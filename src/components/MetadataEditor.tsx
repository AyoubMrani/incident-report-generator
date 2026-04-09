import React, { useState, useEffect } from 'react';
import { ReportMetadata, StoredCategoryOption, StoredMetadataField } from '../types';
import { Plus, Trash2 } from 'lucide-react';

interface Props {
  metadata: ReportMetadata;
  onChange: (metadata: ReportMetadata) => void;
}

const DEFAULT_CATEGORIES = [
  'Application',
  'Hardware',
  'Network',
  'Software',
  'Database',
];

export function MetadataEditor({ metadata, onChange }: Props) {
  const [customFields, setCustomFields] = useState<StoredMetadataField[]>([]);
  const [customCategories, setCustomCategories] = useState<StoredCategoryOption[]>([]);
  const [temporaryFieldIds, setTemporaryFieldIds] = useState<Set<string>>(new Set());
  const [showCustomCategoryInput, setShowCustomCategoryInput] = useState(false);
  const [newCategoryLabel, setNewCategoryLabel] = useState('');
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldValue, setNewFieldValue] = useState('');
  const [saveNewField, setSaveNewField] = useState(false);

  // Load custom categories and fields from Supabase (with localStorage fallback)
  useEffect(() => {
    const loadCustomFields = async () => {
      try {
        // Try to fetch from Supabase
        const response = await fetch('/api/custom-fields');
        if (response.ok) {
          const data = await response.json();
          if (data.customCategories && data.customCategories.length > 0) {
            setCustomCategories(data.customCategories);
            localStorage.setItem('customCategories', JSON.stringify(data.customCategories));
          }
          if (data.customFields && data.customFields.length > 0) {
            setCustomFields(data.customFields);
            localStorage.setItem('customMetadataFields', JSON.stringify(data.customFields));
          }
        }
      } catch (err) {
        console.log('Could not fetch from Supabase, using localStorage');
      }

      // Fallback to localStorage if Supabase is not available
      const stored = localStorage.getItem('customCategories');
      if (stored && customCategories.length === 0) {
        setCustomCategories(JSON.parse(stored));
      }
      const storedFields = localStorage.getItem('customMetadataFields');
      if (storedFields && customFields.length === 0) {
        setCustomFields(JSON.parse(storedFields));
      }
    };

    loadCustomFields();
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    onChange({ ...metadata, [name]: value });
  };

  // Save to both localStorage and Supabase
  const saveCustomFieldsToSupabase = async (fields: StoredMetadataField[], categories: StoredCategoryOption[]) => {
    try {
      const response = await fetch('/api/custom-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customFields: fields,
          customCategories: categories,
        }),
      });
      if (!response.ok) {
        console.warn('Failed to sync to Supabase, will try again later');
      }
    } catch (err) {
      console.warn('Could not sync to Supabase:', err);
    }
  };

  const handleAddCustomCategory = () => {
    if (newCategoryLabel.trim()) {
      const newCategory: StoredCategoryOption = {
        id: Date.now().toString(),
        label: newCategoryLabel,
      };
      const updated = [...customCategories, newCategory];
      setCustomCategories(updated);
      localStorage.setItem('customCategories', JSON.stringify(updated));
      saveCustomFieldsToSupabase(customFields, updated);
      onChange({ ...metadata, category: newCategoryLabel });
      setNewCategoryLabel('');
      setShowCustomCategoryInput(false);
    }
  };

  const handleDeleteCategory = (id: string) => {
    const updated = customCategories.filter(c => c.id !== id);
    setCustomCategories(updated);
    localStorage.setItem('customCategories', JSON.stringify(updated));
    saveCustomFieldsToSupabase(customFields, updated);
  };

  const handleAddCustomField = () => {
    if (newFieldName.trim()) {
      const newField: StoredMetadataField = {
        id: Date.now().toString(),
        name: newFieldName,
        label: newFieldName,
      };

      // Always add to UI state
      const updated = [...customFields, newField];
      setCustomFields(updated);

      // Only save to localStorage and Supabase if checkbox is checked
      if (saveNewField) {
        localStorage.setItem('customMetadataFields', JSON.stringify(updated));
        saveCustomFieldsToSupabase(updated, customCategories);
      } else {
        // Track this as a temporary field for this session
        setTemporaryFieldIds(prev => new Set([...prev, newField.id]));
      }

      onChange({ ...metadata, [newFieldName]: newFieldValue });
      setNewFieldName('');
      setNewFieldValue('');
      setSaveNewField(false);
    }
  };

  const handleDeleteField = (id: string) => {
    const isTemporary = temporaryFieldIds.has(id);
    const updated = customFields.filter(f => f.id !== id);
    setCustomFields(updated);

    // If permanent field, update localStorage and Supabase
    if (!isTemporary) {
      localStorage.setItem('customMetadataFields', JSON.stringify(updated));
      saveCustomFieldsToSupabase(updated, customCategories);
    } else {
      // Remove from temporary tracking
      setTemporaryFieldIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
    }
  };

  return (
    <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 mb-6">
      <h2 className="text-lg font-semibold mb-4 text-gray-800">Incident Metadata</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Incident ID</label>
          <input
            type="text"
            name="incident_id"
            value={metadata.incident_id}
            onChange={handleChange}
            placeholder="e.g., INC0383916"
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Title (Short Description)</label>
          <input
            type="text"
            name="title"
            value={metadata.title}
            onChange={handleChange}
            placeholder="e.g., Delete Provisions | Defective ports in NRI"
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Caller Name</label>
          <input
            type="text"
            name="caller"
            value={metadata.caller}
            onChange={handleChange}
            placeholder="e.g., Robin Carlos Steffen"
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Date of Incident</label>
          <input
            type="date"
            name="date"
            value={metadata.date}
            onChange={handleChange}
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
          <div className="flex gap-2">
            <select
              name="category"
              value={metadata.category}
              onChange={handleChange}
              className="flex-1 p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Select Category</option>
              {DEFAULT_CATEGORIES.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
              {customCategories.map(cat => (
                <option key={cat.id} value={cat.label}>{cat.label}</option>
              ))}
              <option value="__other__">Other (Add Custom)</option>
            </select>
          </div>

          {showCustomCategoryInput && (
            <div className="mt-2 flex gap-2">
              <input
                type="text"
                value={newCategoryLabel}
                onChange={(e) => setNewCategoryLabel(e.target.value)}
                placeholder="Enter custom category"
                className="flex-1 p-2 border border-gray-300 rounded-md text-sm"
                onKeyPress={(e) => e.key === 'Enter' && handleAddCustomCategory()}
              />
              <button
                onClick={handleAddCustomCategory}
                className="px-3 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 text-sm"
              >
                Add
              </button>
              <button
                onClick={() => {
                  setShowCustomCategoryInput(false);
                  setNewCategoryLabel('');
                }}
                className="px-3 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 text-sm"
              >
                Cancel
              </button>
            </div>
          )}

          {metadata.category === '__other__' && !showCustomCategoryInput && (
            <button
              onClick={() => setShowCustomCategoryInput(true)}
              className="mt-2 text-sm text-blue-600 hover:text-blue-700"
            >
              + Add custom category
            </button>
          )}

          {customCategories.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {customCategories.map(cat => (
                <div key={cat.id} className="flex items-center gap-1 bg-blue-100 text-blue-700 px-2 py-1 rounded text-xs">
                  {cat.label}
                  <button
                    onClick={() => handleDeleteCategory(cat.id)}
                    className="hover:text-blue-900"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Subcategory</label>
          <input
            type="text"
            name="subcategory"
            value={metadata.subcategory}
            onChange={handleChange}
            placeholder="e.g., Database Issue"
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      </div>

      {/* Custom Fields Section */}
      <div className="mt-6 pt-6 border-t border-gray-200">
        <h3 className="text-sm font-semibold text-gray-800 mb-4">Custom Fields</h3>

        {/* Existing custom fields */}
        {customFields.map(field => {
          const isTemporary = temporaryFieldIds.has(field.id);
          return (
            <div key={field.id} className="flex items-end gap-2 mb-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <label className="block text-xs font-medium text-gray-700">{field.label}</label>
                  {isTemporary && (
                    <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded">This report only</span>
                  )}
                </div>
                <input
                  type="text"
                  value={metadata[field.name] || ''}
                  onChange={(e) => onChange({ ...metadata, [field.name]: e.target.value })}
                  placeholder={`Enter ${field.label}`}
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
                />
              </div>
              <button
                onClick={() => handleDeleteField(field.id)}
                className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-md"
                title={isTemporary ? "Remove this field from this report" : "Remove this field from all reports"}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          );
        })}

        {/* Add new field form */}
        <div className="mt-4 p-4 bg-gray-50 rounded-md">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Field Name (variable)</label>
              <input
                type="text"
                value={newFieldName}
                onChange={(e) => setNewFieldName(e.target.value)}
                placeholder="e.g., severity_level"
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Field Value (default)</label>
              <input
                type="text"
                value={newFieldValue}
                onChange={(e) => setNewFieldValue(e.target.value)}
                placeholder="e.g., High"
                className="w-full p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 mb-3">
            <input
              type="checkbox"
              checked={saveNewField}
              onChange={(e) => setSaveNewField(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-500"
            />
            <span className="text-sm text-gray-700">Save this field for future reports</span>
          </label>

          <button
            onClick={handleAddCustomField}
            disabled={!newFieldName.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            <Plus className="w-4 h-4" />
            Add Field
          </button>
        </div>
      </div>
    </div>
  );
}
