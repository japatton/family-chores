// Vitest global setup.
// happy-dom provides window/document, but a handful of app features need
// stubs that happy-dom doesn't implement out of the box.

// `@testing-library/jest-dom` extends `expect` with DOM-aware matchers
// (`toBeInTheDocument`, `toHaveTextContent`, `toBeVisible`, etc.) so
// tests can express intent at the right granularity instead of doing
// raw `.toBeTruthy()` checks against DOM nodes.
import '@testing-library/jest-dom/vitest'

import { beforeEach } from 'vitest'

// Reset any localStorage state between tests so Zustand `persist` stores
// start clean.
beforeEach(() => {
  window.localStorage.clear()
})
