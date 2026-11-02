import '@testing-library/jest-dom/vitest';

// jsdom にない API。assistant-ui のビューポートと Radix が使う
class ResizeObserverStub implements ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;
