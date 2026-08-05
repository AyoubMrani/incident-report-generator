import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import {AuthProvider} from './auth/AuthContext';
import {ToastProvider} from './ui/Toast';
import './index.css';

// ToastProvider wraps AuthProvider so auth failures can surface as toasts too.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ToastProvider>
  </StrictMode>,
);
