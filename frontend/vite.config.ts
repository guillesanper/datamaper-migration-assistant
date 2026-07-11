import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"
import { visualizer } from "rollup-plugin-visualizer"

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    tailwindcss(),
    // Bundle analyzer - only in analyze mode
    mode === 'analyze' && visualizer({
      open: true,
      filename: 'dist/stats.html',
      gzipSize: true,
      brotliSize: true,
    }),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Core React libraries (highest priority - preload)
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom') || id.includes('react-router')) {
              return 'react-vendor';
            }

            // Lucide React - separate chunk (heavy icons library)
            if (id.includes('lucide-react')) {
              return 'lucide-vendor';
            }

            // React Hot Toast - separate (not critical)
            if (id.includes('react-hot-toast')) {
              return 'toast-vendor';
            }

            // Radix UI components (medium priority)
            if (id.includes('@radix-ui')) {
              return 'radix-vendor';
            }

            // ReactFlow - HEAVY library, separate chunk
            if (id.includes('reactflow') || id.includes('@xyflow') || id.includes('@reactflow')) {
              return 'reactflow-vendor';
            }

            // Motion library
            if (id.includes('motion')) {
              return 'motion-vendor';
            }

            // Data processing libraries
            if (id.includes('papaparse') || id.includes('xlsx')) {
              return 'data-vendor';
            }

            // TanStack libraries
            if (id.includes('@tanstack')) {
              return 'tanstack-vendor';
            }

            // Other node_modules - generic vendor
            return 'vendor';
          }

          // Application code splitting by feature
          if (id.includes('/components/mapping/')) {
            return 'mapping-components';
          }

          if (id.includes('/components/version_control/')) {
            return 'version-control-components';
          }

          if (id.includes('/services/')) {
            return 'services';
          }
        },
        // Optimize chunk naming for better caching
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
    // Target modern browsers for better performance
    target: 'esnext',
    // Optimize chunk size warnings
    chunkSizeWarningLimit: 1000,
    // Enable minification with esbuild for faster builds
    minify: 'esbuild',
    // Esbuild minify options
    esbuild: {
      drop: ['console', 'debugger'],
      legalComments: 'none',
    },
    // Enable CSS code splitting
    cssCodeSplit: true,
    // Optimize CSS minification
    cssMinify: 'lightningcss',
    // Optimize module preloading - disable polyfill for modern browsers
    modulePreload: {
      polyfill: false, // No polyfill for esnext target
      resolveDependencies: (_filename, deps) => {
        // Preload critical dependencies
        return deps.filter(dep => {
          // Only preload vendor chunks, not lazy-loaded routes
          return dep.includes('vendor') || dep.includes('index');
        });
      },
    },
    // Optimize sourcemaps for production debugging
    sourcemap: false,
  },
  optimizeDeps: {
    // Pre-bundle these dependencies for faster dev server startup
    include: [
      'react',
      'react-dom',
      'react-router-dom',
      'reactflow',
      '@xyflow/react',
      'lucide-react',
      'react-hot-toast',
    ],
    // Exclude large dependencies that should be lazy loaded
    exclude: ['papaparse', 'xlsx'],
  },
  // Performance optimization
  server: {
    // Enable HMR for faster development
    hmr: true,
    // Proxy API requests to backend
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
}))