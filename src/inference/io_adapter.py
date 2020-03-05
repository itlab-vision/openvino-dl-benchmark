import os
import abc
import cv2
import numpy as np


class io_adapter(metaclass = abc.ABCMeta):
    def __convert_images(self, shape, data):
        n, c, h, w  = shape
        images = np.ndarray(shape = (len(data), c, h, w))
        for i in range(len(data)):
            image = cv2.imread(data[i])
            if (image.shape[:-1] != (h, w)):
                image = cv2.resize(image, (w, h))
            image = image.transpose((2, 0, 1))
            images[i] = image
        return images


    def __create_list_images(self, input):
        images = []
        input_is_correct = True
        if os.path.exists(input[0]):
            if os.path.isdir(input[0]):
                path = os.path.abspath(input[0])
                images = [os.path.join(path, file) for file in os.listdir(path)]
            elif os.path.isfile(input[0]):
                for image in input:
                    if not os.path.isfile(image):
                        input_is_correct = False
                        break
                    images.append(os.path.abspath(image))
            else:
                input_is_correct = False
        if not input_is_correct:
            raise ValueError('Wrong path to image or to directory with images')
        return images


    def __check_correct_input(self, len_values):
        ideal = len_values[0]
        for len in len_values:
            if len != ideal:
                raise ValueError('Mismatch batch sizes for different input layers')


    def __parse_tensors(self, filename):
        with open(filename, 'r') as file:
            input = file.readlines()
        input = [line.strip() for line in input]
        shape = [int(number) for number in input[0].split(';')]
        input.pop(0)
        value = []
        for str in input:
            value.append([float(number) for number in str.split(';')])
        result = np.array(value, dtype = np.float32)
        result = result.reshape(shape)
        return result


    def prepare_input(self, model, input, batch_size):
        result = {}
        if ':' in input[0]:
            len_values = []
            for str in input:
                key, value = str.split(':')
                file_format = value.split('.')[-1]
                if 'csv' == file_format:
                    value = self.__parse_tensors(value)
                    len_values.append(value.shape[0])
                else:
                    value = value.split(',')
                    len_values.append(len(value))
                    value = self.__create_list_images(value)
                    shape = model.inputs[key].shape
                    value = self.__convert_images(shape, value)
                result.update({key : value})
            self.__check_correct_input(len_values)
        else:
            input_blob = next(iter(model.inputs))
            file_format = input[0].split('.')[-1]
            if 'csv' == file_format:
                value = self.__parse_tensors(input[0])
            else:
                value = self.__create_list_images(input)
                shape = model.inputs[input_blob].shape
                value = self.__convert_images(shape, value)
            result.update({input_blob : value})
        return result


    def _not_valid_result(self, result):
        return result is None


    @abc.abstractmethod
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        pass


    @staticmethod
    def get_io_adapter(model: str, task: str):
        if task == 'feedforward':
            return feedforward_io()
        elif task == 'classification':
            return classification_io()
        elif task == 'detection':
            return detection_io()
        elif task == 'segmentation':
            return segmenatation_io()
        elif task == 'recognition-face':
            return recognition_face_io()
        elif task == 'person-attributes':
            return person_attributes_io()
        elif task == 'age-gender':
            return age_gender_io()


class feedforward_io(io_adapter):
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        return


class classification_io(io_adapter):
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        if (self._not_valid_result(result)):
            log.warning("Model output is processed only for the number iteration = 1")
            return
        result_layer_name = next(iter(model.outputs))
        result = result[result_layer_name]
        log.info('Top {} results: \n'.format(number_top))
        if not labels:
            labels= os.path.join(os.path.dirname(__file__), 'image_net_synset.txt')
        with open(labels, 'r') as f:
            labels_map = [ x.split(sep = ' ', maxsplit = 1)[-1].strip() for x in f ]
        for batch, probs in enumerate(result):
            probs = np.squeeze(probs)
            top_ind = np.argsort(probs)[-number_top:][::-1]
            print("Result for image {}\n".format(batch + 1))
            for id in top_ind:
                det_label = labels_map[id] if labels_map else '#{}'.format(id)
                print('{:.7f} {}'.format(probs[id], det_label))
            print('\n')


class detection_io(io_adapter):
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        if (self._not_valid_result(result)):
            log.warning("Model output is processed only for the number iteration = 1")
            return
        input_layer_name = next(iter(model.inputs))
        result_layer_name = next(iter(model.outputs))
        input = input[input_layer_name]
        result = result[result_layer_name]
        ib, c, h, w = input.shape
        b = result.shape[0]
        images = np.ndarray(shape = (b, h, w, c))
        for i in range(b):
            images[i] = input[i % ib].transpose((1, 2, 0))
        for batch in range(b):
            for obj in result[batch][0]:
                if obj[2] > prob_threshold:
                    image_number = int(obj[0])
                    image = images[image_number]
                    initial_h, initial_w = image.shape[:2]
                    xmin = int(obj[3] * initial_w)
                    ymin = int(obj[4] * initial_h)
                    xmax = int(obj[5] * initial_w)
                    ymax = int(obj[6] * initial_h)
                    class_id = int(obj[1])
                    color = (min(int(class_id * 12.5), 255), min(class_id * 7, 255),
                        min(class_id * 5, 255))
                    cv2.rectangle(image, (xmin, ymin), (xmax, ymax), color, 2)
                    log.info("Bounding boxes for image {0} for object {1}".format(image_number, class_id))
                    log.info("Top left: ({0}, {1})".format(xmin, ymin))
                    log.info("Bottom right: ({0}, {1})".format(xmax, ymax))
        count = 0
        for image in images:
            out_img = os.path.join(os.path.dirname(__file__), 'out_detection_{}.bmp'.format(count + 1))
            count += 1
            cv2.imwrite(out_img, image)
            log.info('Result image was saved to {}'.format(out_img))


class segmenatation_io(io_adapter):
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        if (self._not_valid_result(result)):
            log.warning("Model output is processed only for the number iteration = 1")
            return
        result_layer_name = next(iter(model.outputs))
        result = result[result_layer_name]
        c = 3
        h, w = result.shape[1:]
        if not color_map:
            color_map = os.path.join(os.path.dirname(__file__), 'color_map.txt')
        classes_color_map = []
        with open(color_map, 'r') as f:
            for line in f:
                classes_color_map.append([int(x) for x in line.split()])
        for batch, data in enumerate(result):
            classes_map = np.zeros(shape = (h, w, c), dtype = np.int)
            for i in range(h):
                for j in range(w):
                    pixel_class = int(data[i, j])
                    classes_map[i, j, :] = classes_color_map[min(pixel_class, 20)]
            out_img = os.path.join(os.path.dirname(__file__), 'out_segmentation_{}.bmp'.format(batch + 1))
            cv2.imwrite(out_img, classes_map)
            log.info('Result image was saved to {}'.format(out_img))


class recognition_face_io(io_adapter):
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        if (self._not_valid_result(result)):
            log.warning("Model output is processed only for the number iteration = 1")
            return
        input_layer_name = next(iter(model.inputs))
        result_layer_name = next(iter(model.outputs))
        input = input[input_layer_name]
        result = result[result_layer_name]
        ib, c, h, w = input.shape
        b = result.shape[0]
        images = np.ndarray(shape = (b, h, w, c))
        for i in range(b):
            images[i] = input[i % ib].transpose((1, 2, 0))
        for i, r in enumerate(result):
            image = images[i]
            initial_h, initial_w = image.shape[:2]
            log.info('Landmarks coordinates for {} image'.format(i))
            for j in range (0, len(r), 2):
                index = int(j / 2) + 1
                x = int(r[j] * initial_w)
                y = int(r[j + 1] * initial_h)
                color = (0, 255, 255)
                cv2.circle(image, (x, y), 1, color, -1)
                log.info('Point {0} - ({1}, {2})'.format(index, x, y))
        count = 0
        for image in images:
            out_img = os.path.join(os.path.dirname(__file__), 'out_recognition_face_{}.bmp'.format(count + 1))
            count += 1
            cv2.imwrite(out_img, image)
            log.info('Result image was saved to {}'.format(out_img))


class person_attributes_io(io_adapter):
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        if (self._not_valid_result(result)):
            log.warning("Model output is processed only for the number iteration = 1")
            return
        input_layer_name = next(iter(model.inputs))
        input = input[input_layer_name]
        layer_iter = iter(model.outputs)
        result_attributes = result[next(layer_iter)]
        result_top = result[next(layer_iter)]
        result_bottom = result[next(layer_iter)]
        b = result_attributes.shape[0]
        ib, c, h, w = input.shape
        images = np.ndarray(shape = (b, h, w * 4, c))
        attributes = ["is_male", "has_bag", "has_backpack", "has_hat", "has_longsleeves",
            "has_longpants", "has_longhair", "has_coat_jacket"]
        color_point = (0, 0, 255)
        for i in range(b):
            for x in range(w):
                for y in range(h):
                    images[i][y][x] = input[i % ib].transpose((1, 2, 0))[y][x]
            x_top = int(result_top[i][0] * w)
            y_top = int(result_top[i][1] * h)
            x_bottom = int(result_bottom[i][0] * w)
            y_bottom = int(result_bottom[i][1] * h)
            color_top = (int(images[i][y_top][x_top][0]), int(images[i][y_top][x_top][1]),
                int(images[i][y_top][x_top][2]))
            color_bottom = (int(images[i][y_bottom][x_bottom][0]), int(images[i][y_bottom][x_bottom][1]),
                int(images[i][y_bottom][x_bottom][2]))
            cv2.circle(images[i], (x_top, y_top), 3, color_point, -1)
            cv2.circle(images[i], (x_bottom, y_bottom), 3, color_point, -1)  
            for x in range(w, 2 * w):
                for y in range(0, int(h / 2)):
                    images[i][y][x] = color_top
                    images[i][y + int(h / 2)][x] = color_bottom
            for j, val in enumerate(result_attributes[i]):
                color_attribut = (0, 255 * bool(val > 0.5), 255 * bool(val <= 0.5))
                cv2.putText(images[i], '{0} {1}'.format(attributes[j], bool(val > 0.5)), 
                    (w * 2 + 5, 20 + j * 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color_attribut)
        count = 0
        for image in images:
            out_img = os.path.join(os.path.dirname(__file__), 'out_person_attributes_{}.bmp'.format(count + 1))
            count += 1
            cv2.imwrite(out_img, image)
            log.info('Result image was saved to {}'.format(out_img)) 


class age_gender_io(io_adapter):
    def process_output(self, model, result, input, labels, number_top, 
            prob_threshold, color_map, log):
        if (self._not_valid_result(result)):
            log.warning("Model output is processed only for the number iteration = 1")
            return
        layer_iter = iter(model.outputs)
        result_age = result[next(layer_iter)]
        result_gender = result[next(layer_iter)]
        b = result_age.shape[0]
        gender = ["Male", "Female"]
        for i in range(b):
            log.info('Information for {} image'.format(i))
            log.info('Gender: {}'.format(gender[bool(result_gender[i][0] > 0.5)]))
            log.info('Years: {:.2f}'.format(result_age[i][0][0][0] * 100))
