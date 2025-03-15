import cv2
from ultralytics import YOLO

# Load YOLO Model
model = YOLO('yolo11n.pt')
cap=cv2.VideoCapture(0)

# COCO Classes
classes = {0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane', 5: 'bus', 6: 'train', 7: 'truck', 
           8: 'boat', 9: 'traffic light', 10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench', 
           14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow', 20: 'elephant', 21: 'bear', 
           22: 'zebra', 23: 'giraffe', 24: 'backpack', 25: 'umbrella', 26: 'handbag', 27: 'tie', 28: 'suitcase', 
           29: 'frisbee', 30: 'skis', 31: 'snowboard', 32: 'sports ball', 33: 'kite', 34: 'baseball bat', 
           35: 'baseball glove', 36: 'skateboard', 37: 'surfboard', 38: 'tennis racket', 39: 'bottle', 40: 'wine glass', 
           41: 'cup', 42: 'fork', 43: 'knife', 44: 'spoon', 45: 'bowl', 46: 'banana', 47: 'apple', 48: 'sandwich', 
           49: 'orange', 50: 'broccoli', 51: 'carrot', 52: 'hot dog', 53: 'pizza', 54: 'donut', 55: 'cake', 56: 'chair', 
           57: 'couch', 58: 'potted plant', 59: 'bed', 60: 'dining table', 61: 'toilet', 62: 'tv', 63: 'laptop', 
           64: 'mouse', 65: 'remote', 66: 'keyboard', 67: 'cell phone', 68: 'microwave', 69: 'oven', 70: 'toaster', 
           71: 'sink', 72: 'refrigerator', 73: 'book', 74: 'clock', 75: 'vase', 76: 'scissors', 77: 'teddy bear', 
           78: 'hair drier', 79: 'toothbrush'}

def detection(cap):
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        personCount = 0
        detected_objects = {}

        # Perform Object Detection
        results = model.predict(frame, conf=0.5)
        annotated_frame = results[0].plot()

        for box, cls in zip(results[0].boxes.xyxy, results[0].boxes.cls):
            class_id = int(cls.item())
            obj_name = classes.get(class_id, "Unknown")

            if class_id == 0:
                personCount += 1
            detected_objects[obj_name] = detected_objects.get(obj_name, 0) + 1

        # Print all detected objects separately
        print(f"\nDetected Objects: \n{detected_objects}")
        print(f"Total Persons Detected: {personCount}")

        return {'detected objects': detected_objects, 'total persons': personCount}