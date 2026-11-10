/**
 * jest-expo (SDK 58, Jest 30) with RNTL 14. Expo's native modules come mocked
 * by the preset; the few the app talks to directly are stubbed in jest.setup.ts.
 */
module.exports = {
  preset: "jest-expo",
  setupFiles: ["<rootDir>/jest.setup.tsx"],
  testMatch: ["<rootDir>/__tests__/**/*.test.ts?(x)"],
  transformIgnorePatterns: [
    "node_modules/(?!(?:.pnpm/)?((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg|@tanstack|openapi-fetch|eventsource-parser))",
  ],
  moduleNameMapper: { "^@/assets/(.*)$": "<rootDir>/assets/$1", "^@/(.*)$": "<rootDir>/src/$1" },
};
