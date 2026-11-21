/**
 * jest-expo (SDK 58, Jest 30) with RNTL 14. Expo's native modules come mocked
 * by the preset; the few the app talks to directly are stubbed in jest.setup.ts.
 */
module.exports = {
  preset: "jest-expo",
  setupFiles: ["<rootDir>/jest.setup.tsx"],
  testMatch: ["<rootDir>/__tests__/**/*.test.ts?(x)"],
  transformIgnorePatterns: [
    "node_modules/(?!(?:.pnpm/)?((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg|lucide-react-native|@shopify/react-native-skia|@tanstack|openapi-fetch|eventsource-parser))",
  ],
  moduleNameMapper: {
    "^@/assets/(.*)$": "<rootDir>/assets/$1",
    "^@/(.*)$": "<rootDir>/src/$1",
    // Spec 069: Lucide ships its React Native entry as .mjs, which the preset does not
    // transform; under Jest the package's own CommonJS build is the same icons.
    "^lucide-react-native$": "<rootDir>/node_modules/lucide-react-native/dist/cjs/lucide-react-native.js",
    "^lucide-react-native/icons/(.*)$": "<rootDir>/node_modules/lucide-react-native/dist/cjs/icons/$1.js",
  },
};
