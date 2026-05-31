import React, { useRef } from 'react';
import { ContentBlock, CodeSnippet, CodeDescription } from '../types';
import { Trash2, ArrowUp, ArrowDown, Image as ImageIcon } from 'lucide-react';
import { QuillEditor } from './QuillEditor';

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
          <div className="space-y-2">
            <div>
              <label className="text-xs font-bold text-yellow-400">TITLE (optional)</label>
              <input
                type="text"
                value={block.title || ''}
                onChange={(e) => onChange({ ...block, title: e.target.value })}
                placeholder="Add a section title..."
                className="w-full p-2 border border-gray-300 rounded bg-gray-50 text-sm mb-2"
              />
            </div>
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
          </div>
        );
      case 'paragraph':
        return (
          <div className="space-y-2">
            <div>
              <label className="text-xs font-bold text-yellow-400">TITLE (optional)</label>
              <input
                type="text"
                value={block.title || ''}
                onChange={(e) => onChange({ ...block, title: e.target.value })}
                placeholder="Add a section title..."
                className="w-full p-2 border border-gray-300 rounded bg-gray-50 text-sm mb-2"
              />
            </div>
            <QuillEditor
              content={block.content}
              onChange={(newContent) => onChange({ ...block, content: newContent })}
            />
          </div>
        );
      case 'list':
        const isDescriptionBox = block.label && block.label.trim() !== '';
        return (
          <div className="space-y-2">
            <div>
              <label className="text-xs font-bold text-yellow-400">TITLE (optional)</label>
              <input
                type="text"
                value={block.title || ''}
                onChange={(e) => onChange({ ...block, title: e.target.value })}
                placeholder="Add a section title..."
                className="w-full p-2 border border-gray-300 rounded bg-gray-50 text-sm"
              />
            </div>
            <div className={isDescriptionBox ? 'border-l-4 border-gray-300 pl-4 py-2 bg-gray-50 rounded-r' : ''}>
              {isDescriptionBox && (
                <input
                  type="text"
                  value={block.label || ''}
                  onChange={(e) => onChange({ ...block, label: e.target.value })}
                  placeholder="Label (e.g., [GUXHG] Please delete:)"
                  className="w-full p-1 mb-2 font-semibold bg-transparent border-b border-gray-200 focus:border-blue-500 focus:outline-none"
                />
              )}
              {!isDescriptionBox && (
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
              )}
              <div className={isDescriptionBox ? 'space-y-1' : 'space-y-2'}>
                {block.items.map((item, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className={`${isDescriptionBox ? 'text-gray-500' : 'text-gray-400'} w-6 text-right`}>
                      {isDescriptionBox ? '-' : block.ordered ? `${i + 1}.` : '•'}
                    </span>
                    <input
                      type="text"
                      value={item}
                      onChange={(e) => {
                        const newItems = [...block.items];
                        newItems[i] = e.target.value;
                        onChange({ ...block, items: newItems });
                      }}
                      className={`flex-1 p-1 bg-transparent border-b border-transparent hover:border-gray-200 focus:border-blue-500 focus:outline-none ${
                        isDescriptionBox ? 'text-sm' : ''
                      }`}
                      placeholder="Item..."
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
                  className={`text-sm text-blue-500 hover:text-blue-700 ${
                    isDescriptionBox ? 'ml-4' : 'ml-8'
                  }`}
                >
                  + Add Item
                </button>
              </div>
              {!isDescriptionBox && (
                <div className="mt-2 text-xs text-gray-500" />
              )}
            </div>
          </div>
        );
      case 'incident_example':
        return (
          <div className="space-y-3 bg-blue-50 p-3 rounded border border-blue-100">
            <div>
              <label className="text-xs font-bold text-yellow-400">TITLE (optional)</label>
              <input
                type="text"
                value={block.title || ''}
                onChange={(e) => onChange({ ...block, title: e.target.value })}
                placeholder="Add a section title..."
                className="w-full p-1 border-b border-blue-200 bg-transparent focus:border-blue-500 focus:outline-none text-blue-900 text-sm"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-blue-800">Incident ID:</span>
              <input
                type="text"
                value={block.incident_id}
                onChange={(e) => onChange({ ...block, incident_id: e.target.value })}
                placeholder="INCXXXXXXX"
                className="flex-1 p-1 border-b border-blue-200 bg-transparent focus:border-blue-500 focus:outline-none text-blue-900"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-blue-800">Link:</span>
              <input
                type="url"
                value={block.link || ''}
                onChange={(e) => onChange({ ...block, link: e.target.value })}
                placeholder="https://example.com/incident/INC001"
                className="flex-1 p-1 border-b border-blue-200 bg-transparent focus:border-blue-500 focus:outline-none text-blue-900"
              />
            </div>
          </div>
        );

      case 'code':
        return (
          <div className="space-y-4 bg-gray-900 rounded-md overflow-hidden border border-gray-800 p-4">
            {block.items.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <p className="mb-4">No code or descriptions added yet</p>
                <div className="flex gap-2 justify-center">
                  <button
                    onClick={() => {
                      const newItem: any = { id: crypto.randomUUID(), type: 'code', title: '', header: '', language: 'javascript', content: '' };
                      onChange({ ...block, items: [...block.items, newItem] });
                    }}
                    className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white hover:bg-blue-700 rounded text-sm"
                  >
                    + Code
                  </button>
                  <button
                    onClick={() => {
                      const newItem: any = { id: crypto.randomUUID(), type: 'description', title: '', content: '' };
                      onChange({ ...block, items: [...block.items, newItem] });
                    }}
                    className="flex items-center gap-1 px-3 py-1 bg-purple-600 text-white hover:bg-purple-700 rounded text-sm"
                  >
                    + Description
                  </button>
                </div>
              </div>
            ) : (
              <>
                {block.items.map((item, idx) => (
                  <div key={item.id} className="bg-gray-800 rounded-md overflow-hidden border border-gray-700">
                    {item.type === 'code' ? (
                      <div className="space-y-2">
                        <div className="px-3 pt-3 pb-2 border-b border-gray-700">
                          <label className="text-xs font-bold text-yellow-400 block mb-1">TITLE</label>
                          <input
                            type="text"
                            value={item.title}
                            onChange={(e) => {
                              const newItems = [...block.items];
                              newItems[idx] = { ...item, title: e.target.value };
                              onChange({ ...block, items: newItems });
                            }}
                            placeholder="Enter title here..."
                            className="w-full px-2 py-1 bg-gray-700 text-white font-semibold text-sm focus:outline-none rounded border border-gray-600 placeholder-gray-500 mb-2"
                          />
                          <label className="text-xs font-bold text-gray-400 block mb-1">HEADER</label>
                          <input
                            type="text"
                            value={item.header}
                            onChange={(e) => {
                              const newItems = [...block.items];
                              newItems[idx] = { ...item, header: e.target.value };
                              onChange({ ...block, items: newItems });
                            }}
                            placeholder="Code section header (e.g., Login Handler)"
                            className="w-full px-2 py-1 bg-gray-700 text-white font-semibold text-sm focus:outline-none rounded border border-gray-600 placeholder-gray-500"
                          />
                        </div>
                        <div className="px-3 py-1 flex items-center gap-2">
                          <select
                            value={item.language}
                            onChange={(e) => {
                              const newItems = [...block.items];
                              newItems[idx] = { ...item, language: e.target.value };
                              onChange({ ...block, items: newItems });
                            }}
                            className="bg-gray-700 text-gray-200 text-xs focus:outline-none px-2 py-1 rounded"
                          >
                            <option value="javascript">JavaScript</option>
                            <option value="typescript">TypeScript</option>
                            <option value="python">Python</option>
                            <option value="java">Java</option>
                            <option value="sql">SQL</option>
                            <option value="html">HTML</option>
                            <option value="css">CSS</option>
                            <option value="bash">Bash</option>
                            <option value="json">JSON</option>
                            <option value="xml">XML</option>
                            <option value="php">PHP</option>
                            <option value="csharp">C#</option>
                            <option value="cpp">C++</option>
                            <option value="go">Go</option>
                            <option value="rust">Rust</option>
                            <option value="swift">Swift</option>
                            <option value="kotlin">Kotlin</option>
                            <option value="r">R</option>
                            <option value="scala">Scala</option>
                          </select>
                        </div>
                        <textarea
                          value={item.content}
                          onChange={(e) => {
                            const newItems = [...block.items];
                            newItems[idx] = { ...item, content: e.target.value };
                            onChange({ ...block, items: newItems });
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Tab') {
                              e.preventDefault();
                              const textarea = e.currentTarget;
                              const start = textarea.selectionStart;
                              const end = textarea.selectionEnd;
                              const newContent = item.content.substring(0, start) + '\t' + item.content.substring(end);
                              const newItems = [...block.items];
                              newItems[idx] = { ...item, content: newContent };
                              onChange({ ...block, items: newItems });
                              setTimeout(() => {
                                textarea.selectionStart = textarea.selectionEnd = start + 1;
                              }, 0);
                            }
                          }}
                          placeholder="Write your code here... (Tab for indentation)"
                          className="w-full p-3 bg-gray-900 text-green-400 font-mono text-sm resize-y min-h-64 focus:outline-none focus:ring-1 focus:ring-green-600 placeholder-gray-600"
                          spellCheck="false"
                        />
                      </div>
                    ) : (
                      <div className="p-3 space-y-2">
                        <label className="text-xs font-bold text-yellow-400 block">TITLE</label>
                        <input
                          type="text"
                          value={item.title}
                          onChange={(e) => {
                            const newItems = [...block.items];
                            newItems[idx] = { ...item, title: e.target.value };
                            onChange({ ...block, items: newItems });
                          }}
                          placeholder="Enter title here..."
                          className="w-full px-2 py-1 bg-gray-700 text-white font-semibold text-sm focus:outline-none rounded border border-gray-600 placeholder-gray-500 mb-2"
                        />
                        <label className="text-xs font-bold text-gray-400 block">DESCRIPTION</label>
                        <QuillEditor
                          content={item.content}
                          onChange={(newContent) => {
                            const newItems = [...block.items];
                            newItems[idx] = { ...item, content: newContent };
                            onChange({ ...block, items: newItems });
                          }}
                        />
                      </div>
                    )}
                    <div className="px-3 py-2 bg-gray-700 flex justify-end border-t border-gray-600">
                      <button
                        onClick={() => {
                          const newItems = block.items.filter((_, i) => i !== idx);
                          onChange({ ...block, items: newItems });
                        }}
                        className="text-xs px-2 py-1 bg-red-600 text-white hover:bg-red-700 rounded"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={() => {
                      const newItem: CodeSnippet = { id: crypto.randomUUID(), type: 'code', title: '', header: '', language: 'javascript', content: '' };
                      onChange({ ...block, items: [...block.items, newItem] });
                    }}
                    className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white hover:bg-blue-700 rounded text-sm"
                  >
                    + Code
                  </button>
                  <button
                    onClick={() => {
                      const newItem: any = { id: crypto.randomUUID(), type: 'description', title: '', content: '' };
                      onChange({ ...block, items: [...block.items, newItem] });
                    }}
                    className="flex items-center gap-1 px-3 py-1 bg-purple-600 text-white hover:bg-purple-700 rounded text-sm"
                  >
                    + Description
                  </button>
                </div>
              </>
            )}
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
          <div className="space-y-2">
            <div>
              <label className="text-xs font-bold text-yellow-400">TITLE (optional)</label>
              <input
                type="text"
                value={block.title || ''}
                onChange={(e) => onChange({ ...block, title: e.target.value })}
                placeholder="Add a section title..."
                className="w-full p-2 border border-gray-300 rounded bg-gray-50 text-sm"
              />
            </div>
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
          </div>
        );
      case 'table':
        return (
          <div className="space-y-2">
            <div>
              <label className="text-xs font-bold text-yellow-400">TITLE (optional)</label>
              <input
                type="text"
                value={block.title || ''}
                onChange={(e) => onChange({ ...block, title: e.target.value })}
                placeholder="Add a section title..."
                className="w-full p-2 border border-gray-300 rounded bg-gray-50 text-sm"
              />
            </div>
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
