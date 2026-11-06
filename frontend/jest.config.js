const nextJest = require('next/jest');

const createJestConfig = nextJest({ dir: './' });

module.exports = createJestConfig({
  testEnvironment: 'node',
  moduleNameMapper: {
    // Resolve the @/ path alias used throughout the source tree
    '^@/(.*)$': '<rootDir>/src/$1',
  },
});
