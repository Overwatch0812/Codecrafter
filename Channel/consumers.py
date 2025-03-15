import json
import cv2
import asyncio
from channels.generic.websocket import WebsocketConsumer,AsyncWebsocketConsumer
from .main2 import detection
from channels.exceptions import StopConsumer

class RandomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected successfully'
        }))
        
        # Initialize camera
        self.camera = cv2.VideoCapture(0)
        
        # Start camera feed processing in a non-blocking way
        asyncio.create_task(self.process_camera_feed())
    
    async def process_camera_feed(self):
        try:
            while True:
                # Process a single frame
                result = detection(self.camera)
                
                # Send detection results to client if needed
                if result:
                    await self.send(text_data=json.dumps({
                        'type': 'detection_result',
                        'data': result
                    }))
                
                # Add a small delay to prevent overwhelming the system
                await asyncio.sleep(0.05)  # ~50 fps
        except Exception as e:
            print(f"Camera feed error: {e}")
            await self.close()

    async def disconnect(self, close_code):
        print('disconnected')
        try:
            if hasattr(self, 'camera'):
                self.camera.release()
        except Exception as e:
            print(f"Error during disconnect: {e}")
        raise StopConsumer()

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        await self.send(text_data=json.dumps({"message": message}))