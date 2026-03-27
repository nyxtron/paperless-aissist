import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { documentsApi } from '../api/client';
import { Send, FileText, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

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

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ChatDocument[]>([]);
  const [searching, setSearching] = useState(false);
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [previewing, setPreviewing] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadDocuments();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await documentsApi.searchPaperless(searchQuery);
        setSearchResults(res.data.results || []);
      } catch (err) {
        console.error('Search failed:', err);
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery]);

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
    setPreviewResult(null);
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

  const handlePreview = async () => {
    if (!selectedDoc) return;
    setPreviewing(true);
    try {
      const res = await documentsApi.getPreview(selectedDoc);
      setPreviewResult(res.data);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message);
    } finally {
      setPreviewing(false);
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
          {/* Search input at top */}
          <div className="p-3 border-b bg-gray-50">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('chat.searchPlaceholder')}
              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Document list / search results */}
          <div className="flex-1 overflow-y-auto">
            {searching ? (
              <div className="p-4 text-sm text-gray-500 text-center">
                {t('chat.searching')}
              </div>
            ) : searchQuery.trim() ? (
              searchResults.length === 0 ? (
                <div className="p-4 text-sm text-gray-500 text-center">
                  {t('chat.noResults')}
                </div>
              ) : (
                searchResults.slice(0, 5).map(doc => (
                  <button
                    key={doc.id}
                    onClick={() => selectDocument(doc.id)}
                    className={`w-full text-left p-3 border-b hover:bg-gray-50 ${
                      selectedDoc === doc.id ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <FileText size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {doc.title || `Document #${doc.id}`}
                        </p>
                        <p className="text-xs text-gray-500">
                          {new Date(doc.created).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                  </button>
                ))
              )
            ) : documents.length === 0 ? (
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

          {/* Refresh button */}
          <div className="p-3 border-t bg-gray-50">
            <button
              onClick={loadDocuments}
              disabled={loadingDocs}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              <RefreshCw size={16} className={loadingDocs ? 'animate-spin' : ''} />
              <span className="text-sm">{t('common.refresh')}</span>
            </button>
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

        {/* Preview Panel */}
        {(selectedDoc || previewResult) && (
          <div className="w-96 bg-white rounded-lg shadow overflow-hidden flex flex-col">
            <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
              <h3 className="font-semibold">{t('chat.previewTitle')}</h3>
              {previewResult ? (
                <button
                  onClick={() => setPreviewResult(null)}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  {t('common.close')}
                </button>
              ) : (
                <button
                  onClick={handlePreview}
                  disabled={previewing || !selectedDoc}
                  className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:opacity-50"
                >
                  {previewing ? t('chat.previewing') : t('chat.preview')}
                </button>
              )}
            </div>
            <div className="p-4 overflow-y-auto flex-1">
              {!previewResult ? (
                <p className="text-sm text-gray-500">{t('chat.previewHint')}</p>
              ) : previewResult.success ? (
                <div className="space-y-2">
                  <p className="text-sm text-green-700">{t('chat.previewSuccess')}</p>
                  {previewResult.steps?.map((step: any, idx: number) => (
                    <div key={idx} className="flex justify-between text-sm">
                      <span>{step.name}</span>
                      <span className="text-gray-500">{step.status}</span>
                    </div>
                  ))}
                  {previewResult.proposed_changes && Object.keys(previewResult.proposed_changes).length > 0 && (
                    <div className="mt-4 pt-4 border-t">
                      <h4 className="text-sm font-medium mb-2">{t('chat.proposedChanges')}</h4>
                      {previewResult.proposed_changes.title && (
                        <p className="text-sm">Title: {previewResult.proposed_changes.title}</p>
                      )}
                      {previewResult.proposed_changes.correspondent && (
                        <p className="text-sm">Correspondent: {previewResult.proposed_changes.correspondent.name}</p>
                      )}
                      {previewResult.proposed_changes.document_type && (
                        <p className="text-sm">Type: {previewResult.proposed_changes.document_type.name}</p>
                      )}
                      {previewResult.proposed_changes.tags && (
                        <p className="text-sm">Tags: {previewResult.proposed_changes.tags.map((t: any) => t.name).join(', ')}</p>
                      )}
                      {previewResult.proposed_changes.custom_fields && (
                        <p className="text-sm">Fields: {previewResult.proposed_changes.custom_fields.map((f: any) => `${f.name}: ${f.value}`).join(', ')}</p>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-red-700">{previewResult.error}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
