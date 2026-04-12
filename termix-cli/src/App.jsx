import React, { useState } from 'react';
import WelcomeScreen from './components/WelcomeScreen.jsx';
import TerminalUI from './components/TerminalUI.jsx';

export default function App() {
  const [phase, setPhase] = useState('welcome'); // 'welcome' | 'terminal'

  const handleEnter = () => {
    setPhase('terminal');
  };

  return (
    <div style={{ width: '100vw', height: '100vh', overflow: 'hidden' }}>
      {phase === 'welcome' && (
        <WelcomeScreen onEnter={handleEnter} />
      )}
      <TerminalUI visible={phase === 'terminal'} />
    </div>
  );
}
