import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, PauseCircle, PlayCircle } from 'lucide-react';

function lineColor(line: string): string {
  const upper = line.toUpperCase();
  if (upper.includes('[ERROR]') || upper.includes(' ERROR ') || upper.includes(':ERROR:')) return 'text-red-400';
  if (upper.includes('[WARNING]') || upper.includes('[WARN]') || upper.includes(' WARNING ')) return 'text-yellow-400';
  return 'text-gray-300';
}

export default function LiveLog() {
  const { t } = useTranslation();
  const [lines, setLines] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);

  pausedRef.current = paused;

  useEffect(() => {
    const es = new EventSource('/api/stats/logs/stream');

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (e) => {
      try {
        const line: string = JSON.parse(e.data);
        setLines((prev) => [...prev, line]);
      } catch {
        // ignore malformed
      }
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, []);

  useEffect(() => {
    if (!paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, paused]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-gray-900">{t('logs.title')}</h1>
          <span
            className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`}
            title={connected ? t('logs.connected') : t('logs.disconnected')}
          />
          <span className="text-sm text-gray-500">{connected ? t('logs.live') : t('logs.disconnected')}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setPaused((p) => !p)}
            className="flex items-center gap-1 px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            {paused ? <PlayCircle size={16} /> : <PauseCircle size={16} />}
            {paused ? t('logs.resume') : t('logs.pause')}
          </button>
          <button
            onClick={() => setLines([])}
            className="flex items-center gap-1 px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            <X size={16} />
            {t('logs.clear')}
          </button>
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg font-mono text-xs overflow-y-auto" style={{ height: 'calc(100vh - 200px)' }}>
        {lines.length === 0 ? (
          <p className="text-gray-500 p-4">{t('logs.emptyState')}</p>
        ) : (
          <div className="p-4 space-y-0.5">
            {lines.map((line, i) => (
              <div key={i} className={`whitespace-pre-wrap break-all leading-5 ${lineColor(line)}`}>
                {line}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
