// Vitest global setup.
// happy-dom provides window/document, but a handful of app features need
// stubs that happy-dom doesn't implement out of the box.

import { beforeEach } from 'vitest'

// Reset any localStorage state between tests so Zustand `persist` stores
// start clean.
beforeEach(() => {
  window.localStorage.clear()
})
