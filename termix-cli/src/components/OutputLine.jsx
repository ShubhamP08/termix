import React from 'react';

const typeColors = {
  command: 'var(--green)',
  success: 'var(--green)',
  error: 'var(--red)',
  warn: 'var(--amber)',
  info: 'rgba(0,255,156,0.7)',
  ai: 'var(--blue)',
  system: 'rgba(0,255,156,0.4)',
};

export default function OutputLine({ entry, index }) {
  const color = typeColors[entry.type] || 'var(--green)';
  const isCommand = entry.type === 'command';

  return (
    <div style={{
      marginBottom: isCommand ? 2 : 8,
      animation: `slideInUp 0.15s ease forwards`,
      animationDelay: `${Math.min(index * 0.02, 0.3)}s`,
      opacity: 0,
      animationFillMode: 'forwards',
    }}>
      {isCommand ? (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          color: 'var(--green)',
        }}>
          <span style={{ color: 'rgba(0,255,156,0.5)', userSelect: 'none' }}>
            dev@termix:~$
          </span>
          <span style={{ color: 'var(--green)', fontWeight: 500 }}>
            {entry.text}
          </span>
        </div>
      ) : (
        <div>
          {entry.lines?.map((line, i) => (
            <div key={i} style={{
              color,
              paddingLeft: 4,
              lineHeight: '1.6',
              whiteSpace: 'pre',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              opacity: line === '' ? 0.3 : 1,
            }}>
              {line === '' ? '\u00A0' : line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
