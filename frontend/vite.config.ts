import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],server:{host:'127.0.0.1',port:5174,strictPort:true,proxy:{'/api':'http://127.0.0.1:'+(process.env.QUANT_API_PORT||'8000')}},build:{rollupOptions:{output:{manualChunks(id){if(id.includes('node_modules')&&(/recharts|d3-|victory|react-smooth/.test(id)))return 'charts';}}}}});
