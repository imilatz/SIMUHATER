#include <Servo.h>

// Pin definitions
const int THROTTLE_PIN = A0;
const int PROP_PIN = A1;
const int MIXTURE_PIN = A2;

// Smoothing settings
const int SAMPLES = 10;
int throttleReadings[SAMPLES];
int propReadings[SAMPLES];
int mixtureReadings[SAMPLES];

// Indices for each control
int throttleIndex = 0;
int propIndex = 0;
int mixtureIndex = 0;

// Running totals
int throttleTotal = 0;
int propTotal = 0;
int mixtureTotal = 0;

// Calibration values (we'll auto-calibrate)
int mixtureMin = 1023, mixtureMax = 0;    // For your potentiometer

// Track totals for each control
int totals[3] = {0, 0, 0};

// Flag for which controls are connected
const bool THROTTLE_CONNECTED = false;
const bool PROP_CONNECTED = false;
const bool MIXTURE_CONNECTED = true;  // Only A2 is connected

// Just using A2 for now
const int POT_PIN = A2;

void setup() {
  Serial.begin(115200);
  pinMode(THROTTLE_PIN, INPUT);
  pinMode(PROP_PIN, INPUT);
  pinMode(MIXTURE_PIN, INPUT);
  
  // Initialize all reading arrays
  for (int i = 0; i < SAMPLES; i++) {
    throttleReadings[i] = 0;
    propReadings[i] = 0;
    mixtureReadings[i] = 0;
  }
}

int smoothReading(int pin, int readings[], int &total, int &index) {
  // Subtract the last reading
  total = total - readings[index];
  // Read from the sensor
  readings[index] = analogRead(pin);
  // Add the reading to the total
  total = total + readings[index];
  // Advance to the next position in the array
  index = (index + 1) % SAMPLES;
  
  return total / SAMPLES;
}

void loop() {
  // Get smoothed readings for all controls
  int throttleRaw = smoothReading(THROTTLE_PIN, throttleReadings, throttleTotal, throttleIndex);
  int propRaw = smoothReading(PROP_PIN, propReadings, propTotal, propIndex);
  int mixtureRaw = 1023 - smoothReading(MIXTURE_PIN, mixtureReadings, mixtureTotal, mixtureIndex);
  
  // Handle throttle with reverse
  int throttlePercent;
  if (throttleRaw >= 755) {
    // Forward thrust: 0% to 100%
    throttlePercent = map(throttleRaw, 755, 1022, 0, 100);
  } else {
    // Reverse/brake: -100% to 0%
    throttlePercent = map(throttleRaw, 677, 755, -100, 0);
  }
  
  // Map other controls
  int propPercent = map(propRaw, 0, 636, 0, 100);
  int mixturePercent = map(mixtureRaw, 2, 825, 0, 100);
  
  // Constrain all values
  throttlePercent = constrain(throttlePercent, -100, 100);
  propPercent = constrain(propPercent, 0, 100);
  mixturePercent = constrain(mixturePercent, 0, 100);
  
  // Send all values in CSV format
  Serial.print(throttleRaw);
  Serial.print(",");
  Serial.print(throttlePercent);  // Now ranges from -100 to +100
  Serial.print(",");
  Serial.print(propRaw);
  Serial.print(",");
  Serial.print(propPercent);
  Serial.print(",");
  Serial.print(mixtureRaw);
  Serial.print(",");
  Serial.println(mixturePercent);
  
  delay(20);
} 