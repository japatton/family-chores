import nodeResolve from '@rollup/plugin-node-resolve'
import typescript from '@rollup/plugin-typescript'
import terser from '@rollup/plugin-terser'

export default {
  input: 'src/family-chores-card.ts',
  output: {
    file: 'dist/family-chores-card.js',
    format: 'es',
    sourcemap: false,
    // Lovelace cards are loaded via <script type="module" src="..."> from
    // HA's /local/ directory; `es` output loads directly in modern browsers.
  },
  plugins: [
    nodeResolve({ browser: true }),
    typescript({ tsconfig: './tsconfig.json' }),
    terser({
      format: { comments: false },
      compress: { passes: 2 },
    }),
  ],
}
