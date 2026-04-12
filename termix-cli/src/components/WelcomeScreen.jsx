import React, { useState, useEffect } from 'react';

const TITLE = 'TermiX CLI';

export default function WelcomeScreen({ onEnter }) {
  const [displayed, setDisplayed] = useState('');
  const [showSub, setShowSub] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [exiting, setExiting] = useState(false);

  // Typewriter effect for title
  useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      setDisplayed(TITLE.slice(0, i + 1));
      i++;
      if (i >= TITLE.length) {
        clearInterval(timer);
        setTimeout(() => setShowSub(true), 300);
        setTimeout(() => setShowHint(true), 700);
      }
    }, 80);
    return () => clearInterval(timer);
  }, []);

  const handleEnter = () => {
    if (exiting) return;
    setExiting(true);
    setTimeout(onEnter, 600);
  };

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Enter') handleEnter();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [exiting]);

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'var(--bg-primary)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      animation: exiting ? 'fadeOut 0.6s ease forwards' : 'fadeIn 0.8s ease forwards',
      zIndex: 10,
      overflow: 'hidden',
    }}>
      {/* Scanline overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)',
        zIndex: 1,
      }} />

      {/* Radial glow bg */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 60% 50% at 50% 50%, rgba(0,255,156,0.06) 0%, transparent 70%)',
      }} />

      {/* Corner decorations */}
      {['topleft','topright','bottomleft','bottomright'].map((pos) => (
        <div key={pos} style={{
          position: 'absolute',
          top: pos.includes('top') ? 24 : 'auto',
          bottom: pos.includes('bottom') ? 24 : 'auto',
          left: pos.includes('left') ? 24 : 'auto',
          right: pos.includes('right') ? 24 : 'auto',
          width: 40, height: 40,
          borderTop: pos.includes('top') ? '1px solid rgba(0,255,156,0.2)' : 'none',
          borderBottom: pos.includes('bottom') ? '1px solid rgba(0,255,156,0.2)' : 'none',
          borderLeft: pos.includes('left') ? '1px solid rgba(0,255,156,0.2)' : 'none',
          borderRight: pos.includes('right') ? '1px solid rgba(0,255,156,0.2)' : 'none',
        }} />
      ))}

      {/* Version tag */}
      <div style={{
        position: 'absolute', top: 28, right: 70,
        fontSize: 11, color: 'var(--muted-text)', letterSpacing: 2,
      }}>
        v1.0.0
      </div>

      {/* Main content */}
      <div style={{ position: 'relative', zIndex: 2, textAlign: 'center' }}>
        {/* ASCII art bar */}
        <div style={{
          fontSize: 11, color: 'rgba(0,255,156,0.3)', letterSpacing: 3,
          marginBottom: 20, fontFamily: 'var(--font-mono)',
          opacity: showSub ? 1 : 0, transition: 'opacity 0.5s',
        }}>
          ══════════════════════════════
        </div>

        {/* Title */}
        <h1 style={{
          fontSize: 'clamp(48px, 8vw, 88px)',
          fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.05em',
          color: 'var(--green)',
          textShadow: '0 0 30px var(--green-glow-strong), 0 0 80px var(--green-glow), 0 0 120px rgba(0,255,156,0.05)',
          animation: displayed.length === TITLE.length ? 'glow-pulse 3s ease-in-out infinite' : 'none',
          margin: 0,
          userSelect: 'none',
          minWidth: '6ch',
        }}>
          {displayed}
          {displayed.length < TITLE.length && (
            <span style={{ animation: 'blink 1s step-end infinite', marginLeft: 2 }}>▋</span>
          )}
        </h1>

        {/* Subtitle */}
        <div style={{
          marginTop: 16,
          fontSize: 14,
          color: 'rgba(0,255,156,0.5)',
          letterSpacing: '0.3em',
          textTransform: 'uppercase',
          opacity: showSub ? 1 : 0,
          transform: showSub ? 'translateY(0)' : 'translateY(10px)',
          transition: 'opacity 0.6s ease, transform 0.6s ease',
        }}>
          Terminal-style AI Developer Tool
        </div>

        {/* Divider */}
        <div style={{
          margin: '32px auto',
          width: showSub ? 200 : 0,
          height: 1,
          background: 'linear-gradient(90deg, transparent, rgba(0,255,156,0.4), transparent)',
          transition: 'width 0.8s ease',
        }} />

        {/* Press Enter hint */}
        <div style={{
          fontSize: 13,
          color: 'rgba(0,255,156,0.4)',
          letterSpacing: '0.25em',
          opacity: showHint ? 1 : 0,
          transition: 'opacity 0.8s ease',
          cursor: 'pointer',
        }} onClick={handleEnter}>
          <span style={{ animation: 'blink 1.5s step-end infinite', marginRight: 8 }}>▶</span>
          PRESS ENTER TO START
          <span style={{ animation: 'blink 1.5s step-end infinite 0.75s', marginLeft: 8 }}>◀</span>
        </div>

        {/* Quick start keys */}
        <div style={{
          marginTop: 40,
          display: 'flex', gap: 20, justifyContent: 'center',
          opacity: showHint ? 0.4 : 0,
          transition: 'opacity 1s ease',
          fontSize: 11,
          color: 'var(--muted-text)',
          letterSpacing: 1,
        }}>
          {['[ENTER] Start', '[ESC] Exit', '[F1] Help'].map(k => (
            <span key={k}>{k}</span>
          ))}
        </div>
      </div>

      {/* Bottom status bar */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        height: 28,
        background: 'rgba(0,255,156,0.04)',
        borderTop: '1px solid rgba(0,255,156,0.08)',
        display: 'flex', alignItems: 'center',
        padding: '0 20px',
        justifyContent: 'space-between',
        fontSize: 10,
        color: 'var(--muted-text)',
        letterSpacing: 1,
      }}>
        <span>TERMIX SHELL v1.0.0</span>
        <span style={{ color: 'rgba(0,255,156,0.3)' }}>● READY</span>
        <span>{new Date().toLocaleDateString()}</span>
      </div>
    </div>
  );
}
