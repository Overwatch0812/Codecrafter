import json
import cv2
import asyncio
import datetime
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from .main2 import detection
from channels.exceptions import StopConsumer
from .bof import simulate_bof_response
from .audio import AudioFrequencyDetector
from .upload import uploadImage

class RandomConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alert_counter = 0
        self.frequency = None
        self.bof_data = None
        self.camera_data = None
        self.imgCount = 1
        self.last_alert_time = None
        self.last_alert_type = None
        self.threat_cooldown = 30  # Seconds to wait before sending another alert of the same type
        self.high_threat_cooldown = 10  # Shorter cooldown for high threats
        self.pending_threats = []  # Queue to store pending threats for evaluation

    async def connect(self):
        self.tasks = []
        self.camera = None
        
        await self.accept()
        
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected successfully'
        }))
        
        try:
            await self.initialize_camera()
            
            camera_task = asyncio.create_task(self.process_camera_feed())
            bof_task = asyncio.create_task(self.process_bof())
            audio_task = asyncio.create_task(self.process_micro())
            
            # Replace the unified alert sender with the threat evaluator
            threat_task = asyncio.create_task(self.evaluate_threats())
            
            self.tasks.append(camera_task)
            self.tasks.append(bof_task)
            self.tasks.append(audio_task)
            self.tasks.append(threat_task)
            
        except Exception as e:
            print(f"Error during connection: {e}")
            await self.close()

    async def initialize_camera(self):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if self.camera:
                    self.camera.release()
                
                self.camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not self.camera.isOpened():
                    raise Exception("Failed to open camera")
                
                ret, _ = self.camera.read()
                if not ret:
                    raise Exception("Camera opened but can't read frames")
                    
                print("Camera initialized successfully")
                return True
            except Exception as e:
                print(f"Camera initialization error (attempt {attempt+1}/{max_attempts}): {e}")
                if self.camera:
                    self.camera.release()
                    self.camera = None
                await asyncio.sleep(1)
        
        print("Failed to initialize camera after multiple attempts")
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

    def calculate_threat_score(self, alert_data):
        """Calculate a numerical threat score to prioritize alerts"""
        score = 0
        
        # Base score from overall severity
        severity_scores = {"none": 0, "low": 20, "medium": 50, "high": 80}
        score += severity_scores.get(alert_data["severity"], 0)
        
        # Add points for specific threats - INCREASED WEIGHTAGE FOR WEAPONS
        if "knife" in str(alert_data["sensorData"]["video"]["detection"]):
            score += 150  # Highest priority for knife detection
        
        if "scissors" in str(alert_data["sensorData"]["video"]["detection"]):
            score += 120  # High priority for scissors
            
        if "fire" in str(alert_data["sensorData"]["video"]["detection"]):
            score += 130  # High priority for fire
            
        # MEDIUM PRIORITY FOR CROWD
        if alert_data["sensorData"]["video"]["detection"] and alert_data["sensorData"]["video"]["detection"].get("is crowded", False):
            score += 60  # Medium priority for crowding
        
        # LOWER PRIORITY FOR BOF
        if alert_data["sensorData"]["bof"]:
            bof_type = alert_data["sensorData"]["bof"].get("Event Type", "")
            bof_intensity = float(alert_data["sensorData"]["bof"].get("Intensity (dB)", 0))
            
            if "explosion" in bof_type.lower():
                score += 70  # Still relatively high for explosions
            elif "gunshot" in bof_type.lower():
                score += 70  # Still relatively high for gunshots
            elif bof_intensity > 70:
                score += 40  # Medium-low priority
            elif bof_intensity > 40:
                score += 20  # Low priority
        
        # Audio frequency detection
        # Audio frequency detection in calculate_threat_score method
        if alert_data["sensorData"]["audio"]["frequency"]:
            try:
                freq = float(alert_data["sensorData"]["audio"]["frequency"])
                if freq > 2000:
                    score += 30  # Higher impact for very high frequencies
                elif freq > 1200:
                    score += 20  # Medium-high impact
                elif freq > 700:  # LOWERED THRESHOLD FROM 1500 to 700
                    score += 15  # Medium impact for frequencies above 700 Hz
            except (ValueError, TypeError):
                pass

        
        return score

    def create_threat_alert(self):
        """Create an alert with threat assessment"""
        weather_conditions = ["Clear", "Cloudy", "Foggy", "Rainy"]
        weather = {
            "temp": round(random.uniform(10, 30), 1),
            "conditions": random.choice(weather_conditions)
        }
        
        alert_types, descriptions, severities = [], [], []
        frame, detected_objects = None, []
        threat_details = []
        
        # Capture frame for potential upload
        if self.camera and self.camera.isOpened():
            ret, frame = self.camera.read()
            if not ret:
                frame = None
        
        # Process camera data
        if self.camera_data:
            detected_objects = self.camera_data.get("detected objects", [])
            is_crowded = self.camera_data.get('is crowded', False)
            is_fire = self.camera_data.get('is fire', False)
            
            if is_crowded:
                alert_types.append("crowd")
                descriptions.append("Crowd detected. ")
                severities.append("medium")
                threat_details.append({"type": "crowd", "severity": "medium"})

            if is_fire:
                alert_types.append("fire")
                descriptions.append("Fire detected. ")
                severities.append("high")
                threat_details.append({"type": "fire", "severity": "high"})
            
            if "knife" in detected_objects:
                alert_types.append("weapon")
                descriptions.append("Knife detected. ")
                severities.append("high")
                threat_details.append({"type": "weapon", "severity": "high", "object": "knife"})
                
            if "scissors" in detected_objects:
                alert_types.append("weapon")
                descriptions.append("Scissors detected. ")
                severities.append("high")
                threat_details.append({"type": "weapon", "severity": "high", "object": "scissors"})
        
        # Process BOF data
        if self.bof_data:
            bof_type = self.bof_data.get("Event Type", "unknown")
            bof_intensity = float(self.bof_data.get("Intensity (dB)", 0))
            
            alert_types.append("anomaly")
            descriptions.append(f"BOF {bof_type} detected. ")
            
            if bof_intensity > 70:
                severity = "high"
            elif bof_intensity > 20:
                severity = "medium"
            else:
                severity = "low"
                
            severities.append(severity)
            threat_details.append({
                "type": "bof", 
                "event": bof_type, 
                "intensity": bof_intensity,
                "severity": severity
            })
        
        # Process audio frequency data
        if self.frequency and self.frequency > 0:
            try:
                freq = float(self.frequency)
                if freq > 700:  # LOWERED THRESHOLD FROM 1500 to 700
                    alert_types.append("audio_anomaly")
                    descriptions.append(f"Unusual audio frequency: {freq:.1f} Hz. ")
                    
                    if freq > 2000:  # Kept high threshold for "high" severity
                        severity = "high"
                    elif freq > 1200:  # Medium-high severity
                        severity = "medium-high"
                    else:  # Medium severity for frequencies between 700-1200
                        severity = "medium"
                        
                    severities.append(severity)
                    threat_details.append({
                        "type": "audio", 
                        "frequency": freq,
                        "severity": severity
                    })
            except ValueError:
                pass
        
        audio_severity = "none"
        if self.frequency and self.frequency > 0:
            freq = float(self.frequency) if isinstance(self.frequency, (int, float, str)) else 0
            if freq > 2000:
                audio_severity = "high"
            elif freq > 1200:
                audio_severity = "medium-high"
            elif freq > 700:  # LOWERED THRESHOLD FROM 1500 to 700
                audio_severity = "medium"
            elif freq > 0:
                audio_severity = "low"

        # Calculate overall severity
        severity_weights = {"none": 0, "low": 0.3, "medium": 0.6, "high": 0.9}
        
        if not severities:
            overall_severity = "none"
        else:
            avg_weight = sum(severity_weights.get(s.lower(), 0) for s in severities) / len(severities)
            
            if avg_weight >= 0.7:
                overall_severity = "high"
            elif avg_weight >= 0.4:
                overall_severity = "medium"
            elif avg_weight > 0:
                overall_severity = "low"
            else:
                overall_severity = "none"
        
        # Determine audio severity for the sensor data section
        audio_severity = "none"
        if self.frequency and self.frequency > 0:
            freq = float(self.frequency) if isinstance(self.frequency, (int, float, str)) else 0
            if freq > 2500:
                audio_severity = "high"
            elif freq > 1500:
                audio_severity = "medium"
            elif freq > 0:
                audio_severity = "low"
        
        # Create the alert object
        alert = {
            "type": alert_types or ["none"],
            "severity": overall_severity,
            "timestamp": datetime.datetime.now().isoformat(),
            "location": "Security System",
            "description": "".join(descriptions) or "No alerts detected.",
            "sensorData": {
                "video": {"active": self.camera is not None and self.camera.isOpened(), "detection": self.camera_data},
                "bof": self.bof_data,
                "audio": {"frequency": self.frequency, "severity": audio_severity},
                "vibration": bool(random.getrandbits(1)),
                "thermal": bool(random.getrandbits(1)),
                "weather": weather
            },
            "status": "unresolved",
            "thumbnail": "/api/placeholder/300/200",
            "threatDetails": threat_details
        }
        
        # Calculate threat score
        threat_score = self.calculate_threat_score(alert)
        
        # Check for weapons and fire as critical threats
        has_weapon = any(obj in ["knife", "scissors"] for obj in detected_objects)
        has_fire = self.camera_data.get('is fire', False) if self.camera_data else False
        
        return {
            "alert": alert,
            "frame": frame,
            "threat_score": threat_score,
            "has_critical_threat": has_weapon or has_fire or overall_severity == "high",
            "threat_type": "+".join(alert_types) if alert_types else "none"
        }

    async def evaluate_threats(self):
        """Continuously evaluate threats and only send the most severe ones"""
        try:
            while True:
                # Create a threat assessment
                threat_data = self.create_threat_alert()
                alert = threat_data["alert"]
                frame = threat_data["frame"]
                threat_score = threat_data["threat_score"]
                has_critical = threat_data["has_critical_threat"]
                threat_type = threat_data["threat_type"]
                
                current_time = datetime.datetime.now()
                
                # Determine if we should send this alert
                should_send = False
                
                # Always send critical threats (but respect cooldown)
                if has_critical:
                    if self.last_alert_time is None or (current_time - self.last_alert_time).total_seconds() > self.high_threat_cooldown:
                        should_send = True
                        print(f"CRITICAL THREAT DETECTED! Score: {threat_score}")
                # For non-critical, use a higher threshold and longer cooldown
                elif threat_score >= 50:  # Medium or higher threat
                    if (self.last_alert_time is None or 
                        (current_time - self.last_alert_time).total_seconds() > self.threat_cooldown or
                        (threat_type != self.last_alert_type)):  # Different type of threat
                        should_send = True
                        print(f"Significant threat detected. Score: {threat_score}")
                
                # Send the alert if it meets our criteria
                if should_send:
                    # Upload image for significant threats
                    if frame is not None:
                        print(f"Uploading image for threat (score: {threat_score})")
                        wc_url = uploadImage(frame, f"threat_{self.imgCount}")
                        self.imgCount += 1
                        if wc_url:
                            alert['thumbnail'] = wc_url
                            print(f"Image uploaded: {wc_url}")
                    
                    # Add threat score to the alert
                    alert['threatScore'] = threat_score
                    
                    # Send the alert
                    await self.send(text_data=json.dumps({
                        'type': 'alert',
                        'data': alert
                    }))
                    
                    # Update tracking variables
                    self.last_alert_time = current_time
                    self.last_alert_type = threat_type
                    print(f"Alert sent at {current_time.isoformat()}")
                else:
                    # For debugging - show what was detected but not sent
                    if threat_score > 0:
                        print(f"Threat detected but not sent. Score: {threat_score}, Type: {threat_type}")
                
                # Wait before next evaluation
                await asyncio.sleep(1)  # Check every second, but only send based on criteria
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Threat evaluation error: {e}")

    async def process_camera_feed(self):
        try:
            frame_count = 0
            consecutive_errors = 0
            max_consecutive_errors = 5
            
            while True:
                if not self.camera:
                    print("Camera not initialized")
                    await asyncio.sleep(1)
                    await self.initialize_camera()
                    continue
                    
                if not self.camera.isOpened():
                    print("Camera not opened")
                    if not await self.initialize_camera():
                        await asyncio.sleep(2)
                        continue
                
                try:
                    ret, frame = self.camera.read()
                    if not ret:
                        consecutive_errors += 1
                        print(f"Failed to read frame. Consecutive errors: {consecutive_errors}")
                        
                        if consecutive_errors >= max_consecutive_errors:
                            print("Too many consecutive errors, reinitializing camera...")
                            await self.release_camera()
                            await asyncio.sleep(1)
                            await self.initialize_camera()
                            consecutive_errors = 0
                        
                        await asyncio.sleep(1)
                        continue
                    
                    consecutive_errors = 0
                    
                    result = detection(self.camera)
                    frame_count += 1
                    
                    if result:
                        self.camera_data = result
                
                except Exception as e:
                    print(f"Error processing frame: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        print("Too many errors, reinitializing camera...")
                        await self.release_camera()
                        await asyncio.sleep(1)
                        await self.initialize_camera()
                        consecutive_errors = 0
                
                await asyncio.sleep(0.1)  # 10 fps processing
        except asyncio.CancelledError:
            await self.release_camera()
            raise
        except Exception as e:
            print(f"Camera feed error: {e}")

    async def process_bof(self):
        try:
            last_bof_time = datetime.datetime.now() - datetime.timedelta(seconds=40)  # Start ready to generate
            bof_interval = 40  # seconds between BOF responses
            
            while True:
                current_time = datetime.datetime.now()
                time_since_last_bof = (current_time - last_bof_time).total_seconds()
                
                if time_since_last_bof >= bof_interval:
                    result = await simulate_bof_response()
                    
                    if result:
                        self.bof_data = result
                        last_bof_time = current_time
                        print(f"BOF data updated at {current_time.isoformat()}: {result}")
                
                # Clear stale BOF data after a while
                if self.bof_data and time_since_last_bof > bof_interval + 20:
                    print("Clearing stale BOF data")
                    self.bof_data = None
                
                await asyncio.sleep(1)  # Check every second, but only update every 40 seconds
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"BOF processing error: {e}")

    async def process_micro(self):
        try:
            # Initialize the audio detector
            print("Initializing audio detector...")
            audio_detector = AudioFrequencyDetector()
            print("Audio detector initialized successfully")
            
            while True:
                try:
                    # Check what methods are available in the AudioFrequencyDetector class
                    # Common method names might be: get_frequency, analyze, process, etc.
                    # Let's try the most likely method names:
                    
                    # Try method 1: get_frequency
                    if hasattr(audio_detector, 'get_frequency'):
                        frequency = audio_detector.get_frequency()
                    # Try method 2: analyze
                    elif hasattr(audio_detector, 'analyze'):
                        frequency = audio_detector.analyze()
                    # Try method 3: process
                    elif hasattr(audio_detector, 'process'):
                        frequency = audio_detector.process()
                    # Try method 4: detect (without _frequency)
                    elif hasattr(audio_detector, 'detect'):
                        frequency = audio_detector.detect()
                    else:
                        # If none of the expected methods exist, log the available methods
                        methods = [method for method in dir(audio_detector) 
                                if callable(getattr(audio_detector, method)) and not method.startswith('__')]
                        print(f"Available methods in AudioFrequencyDetector: {methods}")
                        frequency = None
                    
                    if frequency is not None and frequency > 0:
                        self.frequency = frequency
                        print(f"Detected audio frequency: {frequency} Hz")
                    else:
                        # If no significant frequency detected, log occasionally
                        if random.random() < 0.01:
                            print("No significant audio frequency detected")
                except Exception as e:
                    print(f"Error detecting audio frequency: {e}")
                    # Try to reinitialize the audio detector if it fails
                    try:
                        print("Reinitializing audio detector...")
                        audio_detector = AudioFrequencyDetector()
                    except Exception as reinit_error:
                        print(f"Failed to reinitialize audio detector: {reinit_error}")
                
                await asyncio.sleep(0.5)  # Check every half second
                
        except asyncio.CancelledError:
            # Clean up audio resources if needed
            if 'audio_detector' in locals() and hasattr(audio_detector, 'close'):
                audio_detector.close()
            raise
        except Exception as e:
            print(f"Audio processing error: {e}")


    async def disconnect(self, close_code):
        print('Disconnecting, cleaning up resources...')
        
        for task in self.tasks:
            try:
                task.cancel()
            except Exception as e:
                print(f"Error cancelling task: {e}")
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        await self.release_camera()
        
        self.tasks.clear()
        
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
