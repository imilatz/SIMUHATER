#include <Arduino.h>
#include <EEPROM.h>

// Pin definitions
const int PIN_X = 1;
const int PIN_Y = 2;
const int PIN_SW = 5;

// ADC settings
const int ADC_RESOLUTION = 12;
const int ADC_MAX = (1 << ADC_RESOLUTION) - 1;
const int SAMPLE_COUNT = 10;

// Calibration structure
struct CalibrationData {
  int xMin;
  int xMax;
  int xCenter;
  int yMin;
  int yMax;
  int yCenter;
  bool isCalibrated;
};

// Global variables
CalibrationData calibration;
int xSamples[SAMPLE_COUNT];
int ySamples[SAMPLE_COUNT];
int sampleIndex = 0;

// Deadzone settings (in percentage of full range)
const float DEADZONE_PERCENT = 5.0;
int deadzoneRange;

// Switch debouncing
bool lastSwitchState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long DEBOUNCE_DELAY = 50;

// Calibration mode
bool inCalibrationMode = false;
unsigned long calibrationStartTime = 0;
const unsigned long CALIBRATION_DURATION = 5000; // 5 seconds

void setup() {
  Serial.begin(115200);
  analogReadResolution(ADC_RESOLUTION);
  
  pinMode(PIN_X, INPUT);
  pinMode(PIN_Y, INPUT);
  pinMode(PIN_SW, INPUT_PULLUP);
  
  // Initialize sample arrays
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    xSamples[i] = 0;
    ySamples[i] = 0;
  }
  
  // Calculate deadzone range
  deadzoneRange = (ADC_MAX * DEADZONE_PERCENT) / 100;
  
  // Load calibration from EEPROM
  loadCalibration();
  
  // If not calibrated, set defaults
  if (!calibration.isCalibrated) {
    calibration.xMin = ADC_MAX;
    calibration.xMax = 0;
    calibration.xCenter = ADC_MAX / 2;
    calibration.yMin = ADC_MAX;
    calibration.yMax = 0;
    calibration.yCenter = ADC_MAX / 2;
  }
}

void loadCalibration() {
  EEPROM.begin(sizeof(CalibrationData));
  EEPROM.get(0, calibration);
  EEPROM.end();
}

void saveCalibration() {
  EEPROM.begin(sizeof(CalibrationData));
  EEPROM.put(0, calibration);
  EEPROM.commit();
  EEPROM.end();
}

int getSmoothedReading(int pin, int* samples) {
  samples[sampleIndex] = analogRead(pin);
  
  long sum = 0;
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    sum += samples[i];
  }
  
  return sum / SAMPLE_COUNT;
}

float applyDeadzone(int value, int center) {
  int offset = value - center;
  if (abs(offset) < deadzoneRange) {
    return 0;
  }
  
  // Map the value outside deadzone to full range
  if (offset > 0) {
    return map(offset, deadzoneRange, ADC_MAX - center, 0, 100);
  } else {
    return map(offset, -deadzoneRange, -center, 0, -100);
  }
}

void handleCalibration() {
  int x = getSmoothedReading(PIN_X, xSamples);
  int y = getSmoothedReading(PIN_Y, ySamples);
  
  // Update min/max values
  calibration.xMin = min(calibration.xMin, x);
  calibration.xMax = max(calibration.xMax, x);
  calibration.yMin = min(calibration.yMin, y);
  calibration.yMax = max(calibration.yMax, y);
  
  // Check if calibration time is complete
  if (millis() - calibrationStartTime >= CALIBRATION_DURATION) {
    // Set center points to current position
    calibration.xCenter = x;
    calibration.yCenter = y;
    calibration.isCalibrated = true;
    
    // Save calibration
    saveCalibration();
    
    inCalibrationMode = false;
    Serial.println("CALIBRATION_COMPLETE");
  }
}

void startCalibration() {
  inCalibrationMode = true;
  calibrationStartTime = millis();
  
  // Reset calibration values
  calibration.xMin = ADC_MAX;
  calibration.xMax = 0;
  calibration.yMin = ADC_MAX;
  calibration.yMax = 0;
  
  Serial.println("CALIBRATION_STARTED");
}

void loop() {
  // Read joystick values
  int x = getSmoothedReading(PIN_X, xSamples);
  int y = getSmoothedReading(PIN_Y, ySamples);
  
  // Update sample index
  sampleIndex = (sampleIndex + 1) % SAMPLE_COUNT;
  
  // Handle switch with debouncing
  int switchReading = digitalRead(PIN_SW);
  bool switchChanged = false;
  
  if (switchReading != lastSwitchState) {
    if (millis() - lastDebounceTime > DEBOUNCE_DELAY) {
      lastSwitchState = switchReading;
      switchChanged = true;
      
      // If switch is pressed (LOW) for more than 2 seconds, enter calibration mode
      if (switchReading == LOW) {
        delay(2000);
        if (digitalRead(PIN_SW) == LOW) {
          startCalibration();
          return;
        }
      }
    }
    lastDebounceTime = millis();
  }
  
  if (inCalibrationMode) {
    handleCalibration();
    return;
  }
  
  // Apply calibration and deadzone
  float xNormalized = applyDeadzone(x, calibration.xCenter);
  float yNormalized = applyDeadzone(y, calibration.yCenter);
  
  // Send data
  Serial.print("JOYSTICK,");
  Serial.print(xNormalized);
  Serial.print(",");
  Serial.print(yNormalized);
  Serial.print(",");
  Serial.println(lastSwitchState == LOW ? 1 : 0);
  
  delay(10);
} 