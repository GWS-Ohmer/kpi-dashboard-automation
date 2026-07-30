/**
 * One-time script to set COMBINED_FOLDER_ID in Script Properties
 * Run this once from the Apps Script editor, then delete
 */
function initializeScriptProperties() {
  const props = PropertiesService.getScriptProperties();
  props.setProperty('COMBINED_FOLDER_ID', '1pedfZQ7v-aNVlP2a05he6OI5cL-UlV5-');
  Logger.log('✓ COMBINED_FOLDER_ID set to 1pedfZQ7v-aNVlP2a05he6OI5cL-UlV5-');
  Logger.log('✓ Run loadDashboard() to verify');
}
