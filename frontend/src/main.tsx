import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/outfit';
import 'leaflet/dist/leaflet.css';
import './styles.css';
import './console.css';
import './pages.css';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
