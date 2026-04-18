import cv2
import numpy as np
from ultralytics import YOLO
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class DetectedObject:
    """Represents a detected object with its properties."""
    object_id: str  # Unique identifier for the object
    label: str      # Class label from the detector
    confidence: float  # Confidence score
    bbox_xyxy: Tuple[int, int, int, int]  # Bounding box in xyxy format (x1, y1, x2, y2)
    centroid_xy: Tuple[int, int]  # Centroid coordinates (cx, cy)

class MainObjectDetector:
    """
    Main object detector class for tabletop robot vision using YOLO.
    Handles loading the model, running detections, and visualizing results.
    """

    def __init__(self, model_path: str = "yolo11n.pt", confidence_threshold: float = 0.5):
        """
        Initialize the detector with a YOLO model.

        Args:
            model_path (str): Path to the YOLO model file.
            confidence_threshold (float): Minimum confidence for detections.
        """
        try:
            self.model = YOLO(model_path)
        except Exception as e:
            raise ValueError(f"Failed to load YOLO model from {model_path}: {e}")
        self.confidence_threshold = confidence_threshold

    def compute_centroid(self, bbox_xyxy: Tuple[int, int, int, int]) -> Tuple[int, int]:
        """
        Compute the centroid of a bounding box.

        Args:
            bbox_xyxy (Tuple[int, int, int, int]): Bounding box coordinates (x1, y1, x2, y2).

        Returns:
            Tuple[int, int]: Centroid coordinates (cx, cy).
        """
        x1, y1, x2, y2 = bbox_xyxy
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        return (cx, cy)

    def detect_objects(self, frame: np.ndarray) -> List[DetectedObject]:
        """
        Run object detection on a single frame.

        Args:
            frame (np.ndarray): Input image frame.

        Returns:
            List[DetectedObject]: List of detected objects.
        """
        results = self.model(frame, conf=self.confidence_threshold)
        detections = []

        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for i, box in enumerate(boxes):
                    # Extract bounding box coordinates
                    bbox = box.xyxy[0].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = bbox

                    # Get class label and confidence
                    cls = int(box.cls[0].cpu().numpy())
                    label = self.model.names[cls]
                    conf = float(box.conf[0].cpu().numpy())

                    # Compute centroid
                    centroid = self.compute_centroid((x1, y1, x2, y2))

                    # Create DetectedObject
                    obj = DetectedObject(
                        object_id=f"{label}_{i}",
                        label=label,
                        confidence=conf,
                        bbox_xyxy=(x1, y1, x2, y2),
                        centroid_xy=centroid
                    )
                    detections.append(obj)

        return detections

    def draw_detections(self, frame: np.ndarray, detections: List[DetectedObject]) -> np.ndarray:
        """
        Draw bounding boxes, centroids, and labels on the frame.

        Args:
            frame (np.ndarray): Input image frame.
            detections (List[DetectedObject]): List of detected objects.

        Returns:
            np.ndarray: Annotated frame.
        """
        annotated_frame = frame.copy()
        for obj in detections:
            # Draw bounding box
            cv2.rectangle(annotated_frame, (obj.bbox_xyxy[0], obj.bbox_xyxy[1]),
                          (obj.bbox_xyxy[2], obj.bbox_xyxy[3]), (0, 255, 0), 2)

            # Draw centroid
            cv2.circle(annotated_frame, obj.centroid_xy, 5, (0, 0, 255), -1)

            # Draw label and confidence
            label_text = f"{obj.label} {obj.confidence:.2f}"
            cv2.putText(annotated_frame, label_text, (obj.bbox_xyxy[0], obj.bbox_xyxy[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return annotated_frame

    def run_webcam(self, camera_index: int = 0):
        """
        Run live object detection on webcam feed.

        Args:
            camera_index (int): Index of the camera to use.
        """
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            print(f"Error: Could not open camera with index {camera_index}")
            return

        print("Starting webcam detection. Press 'q' to quit.")

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Failed to read frame from camera.")
                break

            # Run detection
            detections = self.detect_objects(frame)

            # Draw detections
            annotated_frame = self.draw_detections(frame, detections)

            # Print detections to terminal
            if detections:
                print("Detections:")
                for obj in detections:
                    print(f"  {obj.object_id}: {obj.label} at {obj.centroid_xy} (conf: {obj.confidence:.2f})")
            else:
                print("No detections.")

            # Show frame
            cv2.imshow("Object Detection", annotated_frame)

            # Exit on 'q' key
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Example usage
    detector = MainObjectDetector(model_path="yolo11n.pt", confidence_threshold=0.5)
    detector.run_webcam(camera_index=0)

    # Optional: Test on a single image (uncomment to use)
    # image_path = "path/to/your/image.jpg"
    # frame = cv2.imread(image_path)
    # detections = detector.detect_objects(frame)
    # annotated_frame = detector.draw_detections(frame, detections)
    # cv2.imshow("Detections", annotated_frame)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()
    # print("Detections:", detections)