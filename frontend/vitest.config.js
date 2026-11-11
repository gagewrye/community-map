// Test-only config (the app itself has no build step).
export default {
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.js'],
  },
};
