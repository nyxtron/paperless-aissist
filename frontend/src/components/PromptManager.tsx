import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { promptsApi } from '../api/client';
import { Plus, Pencil, Trash2, X, RefreshCw } from 'lucide-react';

interface Prompt {
  id: number;
  name: string;
  prompt_type: string;
  document_type_filter: string | null;
  system_prompt: string;
  user_template: string;
  is_active: boolean;
}

interface TemplateInfo {
  variables: { name: string; description: string }[];
  types: { value: string; description: string }[];
}

export default function PromptManager() {
  const { t } = useTranslation();
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [templates, setTemplates] = useState<TemplateInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null);
  const [samplesMessage, setSamplesMessage] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    prompt_type: 'classify',
    document_type_filter: '',
    system_prompt: '',
    user_template: '',
    is_active: true,
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [promptsRes, templatesRes] = await Promise.all([
        promptsApi.getAll(),
        promptsApi.getTemplates(),
      ]);
      setPrompts(promptsRes.data);
      setTemplates(templatesRes.data);
    } catch (error) {
      console.error('Failed to load prompts:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingPrompt) {
        await promptsApi.update(editingPrompt.id, formData);
      } else {
        await promptsApi.create(formData);
      }
      setShowModal(false);
      setEditingPrompt(null);
      resetForm();
      loadData();
    } catch (error) {
      console.error('Failed to save prompt:', error);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(t('prompts.confirmDelete'))) return;
    try {
      await promptsApi.delete(id);
      loadData();
    } catch (error) {
      console.error('Failed to delete prompt:', error);
    }
  };

  const handleEdit = (prompt: Prompt) => {
    setEditingPrompt(prompt);
    setFormData({
      name: prompt.name,
      prompt_type: prompt.prompt_type,
      document_type_filter: prompt.document_type_filter || '',
      system_prompt: prompt.system_prompt,
      user_template: prompt.user_template,
      is_active: prompt.is_active,
    });
    setShowModal(true);
  };

  const resetForm = () => {
    setFormData({
      name: '',
      prompt_type: 'classify',
      document_type_filter: '',
      system_prompt: '',
      user_template: '',
      is_active: true,
    });
  };

  const handleLoadSamples = async () => {
    if (!confirm(t('prompts.confirmLoadSamples'))) return;
    try {
      const res = await promptsApi.loadSamples();
      setSamplesMessage(t('prompts.samplesLoaded', { created: res.data.created, updated: res.data.updated }));
      setTimeout(() => setSamplesMessage(null), 4000);
      loadData();
    } catch (error) {
      console.error('Failed to load samples:', error);
    }
  };

  const insertVariable = (variable: string, field: 'system' | 'user') => {
    const key = field === 'system' ? 'system_prompt' : 'user_template';
    setFormData({
      ...formData,
      [key]: formData[key] + variable,
    });
  };

  if (loading) {
    return <div className="text-gray-500">{t('common.loading')}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">{t('prompts.title')}</h1>
        <div className="flex items-center gap-2">
          {samplesMessage && (
            <span className="text-sm text-green-700 bg-green-50 px-3 py-1 rounded-lg">{samplesMessage}</span>
          )}
          <button
            onClick={handleLoadSamples}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
          >
            <RefreshCw size={18} />
            {t('prompts.loadSamples')}
          </button>
          <button
            onClick={() => {
              resetForm();
              setEditingPrompt(null);
              setShowModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus size={20} />
            {t('prompts.addPrompt')}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('prompts.colName')}</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('prompts.colType')}</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('prompts.colTypeFilter')}</th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('prompts.colStatus')}</th>
              <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">{t('prompts.colActions')}</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr key={prompt.id} className="border-t hover:bg-gray-50">
                <td className="py-3 px-4 font-medium">{prompt.name}</td>
                <td className="py-3 px-4">
                  <span className="px-2 py-1 bg-gray-100 rounded text-xs">{prompt.prompt_type}</span>
                </td>
                <td className="py-3 px-4 text-gray-600">{prompt.document_type_filter || '-'}</td>
                <td className="py-3 px-4">
                  <span className={`px-2 py-1 rounded text-xs ${prompt.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                    {prompt.is_active ? t('prompts.active') : t('prompts.inactive')}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  <button
                    onClick={() => handleEdit(prompt)}
                    className="p-1 text-gray-600 hover:text-blue-600"
                  >
                    <Pencil size={18} />
                  </button>
                  <button
                    onClick={() => handleDelete(prompt.id)}
                    className="p-1 text-gray-600 hover:text-red-600 ml-2"
                  >
                    <Trash2 size={18} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4">
            <div className="flex justify-between items-center p-4 border-b">
              <h2 className="text-lg font-semibold">{editingPrompt ? t('prompts.editPrompt') : t('prompts.createPrompt')}</h2>
              <button onClick={() => setShowModal(false)} className="text-gray-500 hover:text-gray-700">
                <X size={24} />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-4 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('prompts.labelName')}</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('prompts.labelType')}</label>
                  <select
                    value={formData.prompt_type}
                    onChange={(e) => setFormData({ ...formData, prompt_type: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    {templates?.types.map((type) => (
                      <option key={type.value} value={type.value}>{type.description}</option>
                    ))}
                  </select>
                </div>
              </div>

              {formData.prompt_type === 'type_specific' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('prompts.labelDocTypeFilter')}</label>
                  <input
                    type="text"
                    value={formData.document_type_filter}
                    onChange={(e) => setFormData({ ...formData, document_type_filter: e.target.value })}
                    placeholder={t('prompts.docTypeFilterPlaceholder')}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('prompts.labelSystemPrompt')}</label>
                {templates && (
                  <div className="flex gap-2 mb-2 flex-wrap">
                    {templates.variables.map((v) => (
                      <button
                        key={v.name}
                        type="button"
                        onClick={() => insertVariable(v.name, 'system')}
                        className="text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded hover:bg-blue-100"
                      >
                        {v.name}
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  value={formData.system_prompt}
                  onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
                  required
                  rows={4}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('prompts.labelUserTemplate')}</label>
                {templates && (
                  <div className="flex gap-2 mb-2 flex-wrap">
                    {templates.variables.map((v) => (
                      <button
                        key={v.name}
                        type="button"
                        onClick={() => insertVariable(v.name, 'user')}
                        className="text-xs px-2 py-1 bg-green-50 text-green-600 rounded hover:bg-green-100"
                      >
                        {v.name}
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  value={formData.user_template}
                  onChange={(e) => setFormData({ ...formData, user_template: e.target.value })}
                  required
                  rows={4}
                  placeholder={t('prompts.userTemplatePlaceholder')}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="is_active" className="text-sm text-gray-700">{t('prompts.labelActive')}</label>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
                >
                  {t('common.cancel')}
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  {editingPrompt ? t('prompts.update') : t('prompts.create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
