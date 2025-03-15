import json
import cv2
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from .main2 import detection
from channels.exceptions import StopConsumer
from .bof import simulate_bof_response

class RandomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Store tasks and initialize camera
        self.tasks = []
        self.camera = None
        
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected successfully'
        }))
        
        # Initialize camera
        try:
            await self.initialize_camera()
            
            # Start camera feed processing and BOF tasks
            detection_task = asyncio.create_task(self.process_camera_feed())
            bof_task = asyncio.create_task(self.process_bof())
            
            # Store tasks for proper cleanup
            self.tasks.append(detection_task)
            self.tasks.append(bof_task)
            
        except Exception as e:
            print(f"Error during connection: {e}")
            await self.close()
    
    async def initialize_camera(self):
        try:
            if self.camera:
                self.camera.release()
            
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                raise Exception("Failed to open camera")
            print("Camera initialized successfully")
            return True
        except Exception as e:
            print(f"Camera initialization error: {e}")
            return False
    
    async def release_camera(self):
        if self.camera:
            try:
                self.camera.release()
                result = not self.camera.isOpened()
                if result:
                    print("Camera successfully released")
                else:
                    print("Warning: Camera may not have been properly released")
                self.camera = None
                return result
            except Exception as e:
                print(f"Camera release error: {e}")
                return False
        return True
    
    async def process_camera_feed(self):
        try:
            frame_count = 0
            while True:
                if not self.camera:
                    print("Camera not initialized")
                    await asyncio.sleep(1)
                    continue
                    
                if not self.camera.isOpened():
                    print("Camera not opened")
                    # Try to re-initialize
                    if not await self.initialize_camera():
                        await asyncio.sleep(2)
                        continue
                
                # Process a single frame
                result = detection(self.camera)
                frame_count += 1
                
                # Periodically check camera status
                if frame_count % 100 == 0:
                    if not self.camera.isOpened():
                        print("Camera connection was lost, trying to reinitialize")
                        await self.initialize_camera()
                
                # Send detection results to client if needed
                if result:
                    await self.send(text_data=json.dumps({
                        'type': 'detection_result',
                        'data': result
                    }))
                
                # Add a small delay to prevent overwhelming the system
                await asyncio.sleep(0.05)  # ~20 fps
        except asyncio.CancelledError:
            # Clean release of camera resource during cancellation
            await self.release_camera()
            raise
        except Exception as e:
            print(f"Camera feed error: {e}")
    
    async def process_bof(self):
        try:
            while True:
                # Process BOF - now using async version
                result = await simulate_bof_response()  # Note the 'await' here
                
                # Send BOF results to client
                if result:
                    await self.send(text_data=json.dumps({
                        'type': 'bof_result',
                        'data': result
                    }))
            
            # Small delay between iterations
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"BOF processing error: {e}")
    
    async def disconnect(self, close_code):
        print('Disconnecting, cleaning up resources...')
        
        # Cancel all running tasks first
        for task in self.tasks:
            try:
                task.cancel()
            except Exception as e:
                print(f"Error cancelling task: {e}")
        
        # Wait for all tasks to complete their cancellation
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Explicitly release camera resources after tasks are canceled
        await self.release_camera()
        
        # Clear tasks list
        self.tasks.clear()
        
        # Now raise StopConsumer
        raise StopConsumer()
    
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json.get("message", "")
            
            await self.send(text_data=json.dumps({
                "message": message,
                "type": "response"
            }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                "error": "Invalid JSON received",
                "type": "error"
            }))
        except Exception as e:
            print(f"Error in receive: {e}")
            await self.send(text_data=json.dumps({
                "error": "Server error processing message",
                "type": "error"
            }))