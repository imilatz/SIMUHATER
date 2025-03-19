## Driving Simulator Setup

### Additional Hardware
- Second Arduino Mega 2560 for handbrake
- 10kΩ potentiometer for handbrake
- USB cable for second Arduino

### Handbrake Wiring
1. Connect potentiometer:
   - Left pin → GND
   - Middle pin → A0
   - Right pin → 5V

### Software Setup
1. Upload `handbrake.ino` to second Arduino
2. Note the COM port for handbrake Arduino
3. Update COM port in Python script if needed
4. Select "Driving Simulator" profile

### Game Setup
1. Configure controls:
   - Gas Pedal: Right Trigger
   - Brake Pedal: Left Trigger
   - Handbrake: Right Stick Y 

## Racing Game Setup

### Forza Series
1. Configure in game:
   - Gas: Right Trigger
   - Brake: Left Trigger
   - Handbrake: A Button
   - Set handbrake to "Digital" in ION

### Assetto Corsa
1. Configure in game:
   - Gas: Right Trigger
   - Brake: Left Trigger
   - Handbrake: Right Stick Y
   - Set handbrake to "Analog" in ION 