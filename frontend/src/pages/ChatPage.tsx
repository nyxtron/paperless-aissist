import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { documentsApi } from '../api/client';
import { Send, FileText, Loader2, RefreshCw } from 'lucide-react';

interface ChatDocument {
  id: number;
  title: string;
  created: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatPage() {
  const { t } = useTranslation();
  const [documents, setDocuments] = useState<ChatDocument[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadDocuments();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadDocuments = async () => {
    setLoadingDocs(true);
    try {
      const res = await documentsApi.getChatList();
      setDocuments(res.data.documents || []);
      if (res.data.error) {
        setError(res.data.error);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoadingDocs(false);
    }
  };

  const selectDocument = async (docId: number) => {
    setSelectedDoc(docId);
    setLoadingDoc(true);
    setMessages([]);
    setError(null);

    try {
      const res = await documentsApi.getChatDocument(docId);
      setMessages([
        {
          role: 'assistant',
          content: t('chat.documentLoaded', { title: res.data.title }),
        },
      ]);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoadingDoc(false);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || !selectedDoc || loading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);
    setError(null);

    try {
      const res = await documentsApi.chat(selectedDoc, userMessage);
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.response }]);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      setMessages(prev => [...prev, { role: 'assistant', content: t('chat.errorResponse') }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900">{t('chat.title')}</h1>
        <p className="text-sm text-gray-500">{t('chat.subtitle')}</p>
      </div>

      <div className="flex gap-4 flex-1 min-h-0">
        {/* Document List */}
        <div className="w-64 bg-white rounded-lg shadow overflow-hidden flex flex-col">
          <div className="p-3 border-b bg-gray-50 flex justify-between items-center">
            <h2 className="font-semibold text-sm">{t('chat.selectDocument')}</h2>
            <button
              onClick={loadDocuments}
              disabled={loadingDocs}
              className="p-1 hover:bg-gray-200 rounded disabled:opacity-50"
              title={t('chat.refreshTitle')}
            >
              <RefreshCw size={16} className={loadingDocs ? 'animate-spin' : ''} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {documents.length === 0 ? (
              <div className="p-4 text-sm text-gray-500 text-center">
                {t('chat.noDocuments')}
              </div>
            ) : (
              documents.map(doc => (
                <button
                  key={doc.id}
                  onClick={() => selectDocument(doc.id)}
                  className={`w-full text-left p-3 border-b hover:bg-gray-50 transition-colors ${
                    selectedDoc === doc.id ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <FileText size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {doc.title || t('chat.docFallback', { id: doc.id })}
                      </p>
                      <p className="text-xs text-gray-500">
                        {new Date(doc.created).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex-1 bg-white rounded-lg shadow flex flex-col overflow-hidden">
          {!selectedDoc ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              <div className="text-center">
                <FileText size={48} className="mx-auto mb-4 text-gray-300" />
                <p>{t('chat.emptyState')}</p>
              </div>
            </div>
          ) : (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg p-3 ${
                        msg.role === 'user'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-900'
                      }`}
                    >
                      <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                    </div>
                  </div>
                ))}
                {loadingDoc && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 rounded-lg p-3">
                      <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Loader2 size={16} className="animate-spin" />
                        {t('chat.loadingDocument')}
                      </div>
                    </div>
                  </div>
                )}
                {loading && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 rounded-lg p-3">
                      <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Loader2 size={16} className="animate-spin" />
                        {t('chat.thinking')}
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Error */}
              {error && (
                <div className="px-4 py-2 bg-red-50 text-red-700 text-sm">
                  {error}
                </div>
              )}

              {/* Input */}
              <div className="p-4 border-t">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={t('chat.inputPlaceholder')}
                    disabled={!selectedDoc || loading}
                    className="flex-1 px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
                  />
                  <button
                    onClick={sendMessage}
                    disabled={!selectedDoc || loading || !input.trim()}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Send size={20} />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
