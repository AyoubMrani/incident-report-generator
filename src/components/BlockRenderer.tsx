import React, { useRef } from 'react';
import { ContentBlock } from '../types';
import { Trash2, ArrowUp, ArrowDown, Image as ImageIcon } from 'lucide-react';

interface Props {
  key?: React.Key;
  block: ContentBlock;
  onChange: (block: ContentBlock) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  isFirst: boolean;
  isLast: boolean;
}

export function BlockRenderer({ block, onChange, onRemove, onMoveUp, onMoveDown, isFirst, isLast }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const renderBlockContent = () => {
    switch (block.type) {
      case 'heading':
        return (
          <div className="flex items-center gap-2">
            <select
              value={block.level}
              onChange={(e) => onChange({ ...block, level: parseInt(e.target.value) as 1|2|3|4 })}
              className="p-2 border border-gray-300 rounded bg-gray-50"
            >
              <option value={1}>H1</option>
              <option value={2}>H2</option>
              <option value={3}>H3</option>
              <option value={4}>H4</option>
            </select>
            <input
              type="text"
              value={block.content}
              onChange={(e) => onChange({ ...block, content: e.target.value })}
              placeholder="Heading text..."
              className={`flex-1 p-2 border-b border-transparent hover:border-gray-300 focus:border-blue-500 focus:outline-none bg-transparent font-bold ${
                block.level === 1 ? 'text-2xl' : block.level === 2 ? 'text-xl' : block.level === 3 ? 'text-lg' : 'text-base'
              }`}
            />
          </div>
        );
      case 'paragraph':
        return (
          <textarea
            value={block.content}
            onChange={(e) => onChange({ ...block, content: e.target.value })}
            placeholder="Type paragraph text here..."
            className="w-full p-2 border border-transparent hover:border-gray-300 focus:border-blue-500 focus:outline-none bg-transparent resize-y min-h-[80px]"
          />
        );
      case 'list':
        return (
          <div>
            <div className="mb-2 flex items-center gap-2">
              <label className="text-sm text-gray-600 flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={block.ordered}
                  onChange={(e) => onChange({ ...block, ordered: e.target.checked })}
                />
                Ordered List
              </label>
            </div>
            <div className="space-y-2">
              {block.items.map((item, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-gray-400 w-6 text-right">
                    {block.ordered ? `${i + 1}.` : '•'}
                  </span>
                  <input
                    type="text"
                    value={item}
                    onChange={(e) => {
                      const newItems = [...block.items];
                      newItems[i] = e.target.value;
                      onChange({ ...block, items: newItems });
                    }}
                    className="flex-1 p-1 border-b border-gray-200 focus:border-blue-500 focus:outline-none"
                    placeholder="List item..."
                  />
                  <button
                    onClick={() => {
                      const newItems = block.items.filter((_, idx) => idx !== i);
                      onChange({ ...block, items: newItems.length ? newItems : [''] });
                    }}
                    className="text-gray-400 hover:text-red-500"
                  >
                    &times;
                  </button>
                </div>
              ))}
              <button
                onClick={() => onChange({ ...block, items: [...block.items, ''] })}
                className="text-sm text-blue-500 hover:text-blue-700 ml-8"
              >
                + Add Item
              </button>
            </div>
          </div>
        );
      case 'incident_example':
        return (
          <div className="flex items-center gap-2 bg-blue-50 p-3 rounded border border-blue-100">
            <span className="font-semibold text-blue-800">Incident example:</span>
            <input
              type="text"
              value={block.incident_id}
              onChange={(e) => onChange({ ...block, incident_id: e.target.value })}
              placeholder="INCXXXXXXX"
              className="p-1 border-b border-blue-200 bg-transparent focus:border-blue-500 focus:outline-none text-blue-900"
            />
          </div>
        );
      case 'description_box':
        return (
          <div className="border-l-4 border-gray-300 pl-4 py-2 bg-gray-50 rounded-r">
            <input
              type="text"
              value={block.label}
              onChange={(e) => onChange({ ...block, label: e.target.value })}
              placeholder="Label (e.g., [GUXHG] Please delete:)"
              className="w-full p-1 mb-2 font-semibold bg-transparent border-b border-gray-200 focus:border-blue-500 focus:outline-none"
            />
            <div className="space-y-1">
              {block.items.map((item, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-gray-500">-</span>
                  <input
                    type="text"
                    value={item}
                    onChange={(e) => {
                      const newItems = [...block.items];
                      newItems[i] = e.target.value;
                      onChange({ ...block, items: newItems });
                    }}
                    className="flex-1 p-1 bg-transparent border-b border-transparent hover:border-gray-200 focus:border-blue-500 focus:outline-none text-sm"
                    placeholder="Description item..."
                  />
                  <button
                    onClick={() => {
                      const newItems = block.items.filter((_, idx) => idx !== i);
                      onChange({ ...block, items: newItems.length ? newItems : [''] });
                    }}
                    className="text-gray-400 hover:text-red-500"
                  >
                    &times;
                  </button>
                </div>
              ))}
              <button
                onClick={() => onChange({ ...block, items: [...block.items, ''] })}
                className="text-xs text-blue-500 hover:text-blue-700 ml-4"
              >
                + Add Item
              </button>
            </div>
          </div>
        );
      case 'code':
        return (
          <div className="bg-gray-900 rounded-md overflow-hidden">
            <div className="bg-gray-800 px-3 py-1 flex items-center">
              <input
                type="text"
                value={block.language}
                onChange={(e) => onChange({ ...block, language: e.target.value })}
                placeholder="language (e.g., sql)"
                className="bg-transparent text-gray-300 text-xs focus:outline-none w-24"
              />
            </div>
            <textarea
              value={block.content}
              onChange={(e) => onChange({ ...block, content: e.target.value })}
              placeholder="Paste code here..."
              className="w-full p-3 bg-transparent text-green-400 font-mono text-sm resize-y min-h-[100px] focus:outline-none"
              spellCheck={false}
            />
          </div>
        );
      case 'image':
        const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
          const file = e.target.files?.[0];
          if (file) {
            const reader = new FileReader();
            reader.onloadend = () => {
              onChange({ ...block, data_url: reader.result as string });
            };
            reader.readAsDataURL(file);
          }
        };
        return (
          <div className="border border-gray-200 rounded p-2">
            {block.data_url ? (
              <div className="relative group">
                <img src={block.data_url} alt="Uploaded" className="max-h-64 object-contain mx-auto rounded" />
                <button
                  onClick={() => onChange({ ...block, data_url: '' })}
                  className="absolute top-2 right-2 bg-red-500 text-white p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div 
                className="h-32 border-2 border-dashed border-gray-300 rounded flex flex-col items-center justify-center cursor-pointer hover:bg-gray-50"
                onClick={() => fileInputRef.current?.click()}
              >
                <ImageIcon className="w-8 h-8 text-gray-400 mb-2" />
                <span className="text-sm text-gray-500">Click to upload image</span>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleImageUpload}
                  accept="image/*"
                  className="hidden"
                />
              </div>
            )}
            <input
              type="text"
              value={block.caption}
              onChange={(e) => onChange({ ...block, caption: e.target.value })}
              placeholder="Image caption..."
              className="w-full mt-2 p-2 text-sm text-center border-b border-transparent hover:border-gray-200 focus:border-blue-500 focus:outline-none"
            />
          </div>
        );
      case 'table':
        return (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse border border-gray-300 text-sm">
              <thead>
                <tr>
                  {block.headers.map((header, i) => (
                    <th key={i} className="border border-gray-300 bg-gray-100 p-0">
                      <div className="flex items-center">
                        <input
                          type="text"
                          value={header}
                          onChange={(e) => {
                            const newHeaders = [...block.headers];
                            newHeaders[i] = e.target.value;
                            onChange({ ...block, headers: newHeaders });
                          }}
                          className="w-full p-2 bg-transparent focus:outline-none font-semibold text-center"
                        />
                        <button
                          onClick={() => {
                            if (block.headers.length <= 1) return;
                            const newHeaders = block.headers.filter((_, idx) => idx !== i);
                            const newRows = block.rows.map(row => row.filter((_, idx) => idx !== i));
                            onChange({ ...block, headers: newHeaders, rows: newRows });
                          }}
                          className="px-1 text-gray-400 hover:text-red-500"
                          title="Remove Column"
                        >
                          &times;
                        </button>
                      </div>
                    </th>
                  ))}
                  <th className="border border-gray-300 bg-gray-100 w-8">
                    <button
                      onClick={() => {
                        onChange({
                          ...block,
                          headers: [...block.headers, `Col ${block.headers.length + 1}`],
                          rows: block.rows.map(row => [...row, ''])
                        });
                      }}
                      className="w-full h-full text-blue-500 hover:bg-blue-50"
                      title="Add Column"
                    >
                      +
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, colIndex) => (
                      <td key={colIndex} className="border border-gray-300 p-0">
                        <input
                          type="text"
                          value={cell}
                          onChange={(e) => {
                            const newRows = [...block.rows];
                            newRows[rowIndex][colIndex] = e.target.value;
                            onChange({ ...block, rows: newRows });
                          }}
                          className="w-full p-2 bg-transparent focus:outline-none"
                        />
                      </td>
                    ))}
                    <td className="border border-gray-300 text-center">
                      <button
                        onClick={() => {
                          if (block.rows.length <= 1) return;
                          const newRows = block.rows.filter((_, idx) => idx !== rowIndex);
                          onChange({ ...block, rows: newRows });
                        }}
                        className="text-gray-400 hover:text-red-500"
                        title="Remove Row"
                      >
                        &times;
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button
              onClick={() => {
                onChange({
                  ...block,
                  rows: [...block.rows, Array(block.headers.length).fill('')]
                });
              }}
              className="mt-2 text-sm text-blue-500 hover:text-blue-700"
            >
              + Add Row
            </button>
          </div>
        );
      default:
        return <div>Unknown block type</div>;
    }
  };

  return (
    <div className="group relative bg-white p-4 rounded-lg shadow-sm border border-gray-200 hover:border-blue-300 transition-colors">
      <div className="absolute -left-3 top-1/2 -translate-y-1/2 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={onMoveUp} disabled={isFirst} className="p-1 bg-white border border-gray-200 rounded-full shadow-sm text-gray-500 hover:text-blue-600 disabled:opacity-30">
          <ArrowUp className="w-3 h-3" />
        </button>
        <button onClick={onMoveDown} disabled={isLast} className="p-1 bg-white border border-gray-200 rounded-full shadow-sm text-gray-500 hover:text-blue-600 disabled:opacity-30">
          <ArrowDown className="w-3 h-3" />
        </button>
      </div>
      
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={onRemove} className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded">
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <div className="mb-2">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{block.type.replace('_', ' ')}</span>
      </div>
      
      {renderBlockContent()}
    </div>
  );
}
