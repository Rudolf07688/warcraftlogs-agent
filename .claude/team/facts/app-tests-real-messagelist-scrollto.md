---
id: app-tests-real-messagelist-scrollto
anchors: [file:frontend/src/components/MessageList.tsx]
by: dev-5 Edda
verified: 9107884 2026-11-22
---
App tests that render the real MessageList must stub HTMLElement.prototype.scrollTo (jsdom lacks
it): on 'done' ScrollToQuestion scrolls the question into view, the throw is caught by the
telemetry error boundary and the page silently renders no messages, so assertions fail with an
empty list rather than an error. Also stub ResizeObserver for use-stick-to-bottom. See
App.thinking.test.tsx.
