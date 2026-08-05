/// <reference types="vite/client" />

// Asset imports. Vite resolves these at build time to a fingerprinted URL (or
// an inlined data URI for small files); TypeScript needs to be told they are
// modules that yield a string, or `import logo from './logo.png'` is an error.
declare module '*.png' {
  const src: string;
  export default src;
}
declare module '*.jpg' {
  const src: string;
  export default src;
}
declare module '*.svg' {
  const src: string;
  export default src;
}
declare module '*.webp' {
  const src: string;
  export default src;
}
