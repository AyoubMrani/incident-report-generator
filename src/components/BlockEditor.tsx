import React, { useState } from 'react';
import { ContentBlock, BlockType } from '../types';
import { BlockRenderer } from './BlockRenderer';
import { PlusCircle, FileJson, FileText } from 'lucide-react';

interface Props {
  blocks: ContentBlock[];
  onChange: (blocks: ContentBlock[]) => void;
}

export function BlockEditor({ blocks, onChange }: Props) {
  const [showMenu, setShowMenu] = useState(false);

  const addBlock = (type: BlockType) => {
    const newBlockBase = { id: crypto.randomUUID(), type };
    let newBlock: ContentBlock;

    switch (type) {
      case 'heading':
        newBlock = { ...newBlockBase, type: 'heading', level: 1, content: '' };
        break;
      case 'paragraph':
        newBlock = { ...newBlockBase, type: 'paragraph', content: '' };
        break;
      case 'list':
        newBlock = { ...newBlockBase, type: 'list', ordered: false, items: [''] };
        break;
      case 'incident_example':
        newBlock = { ...newBlockBase, type: 'incident_example', incident_id: '' };
        break;
      case 'description_box':
        newBlock = { ...newBlockBase, type: 'description_box', label: '', items: [''] };
        break;
      case 'code':
        newBlock = { ...newBlockBase, type: 'code', language: 'sql', content: '' };
        break;
      case 'image':
        newBlock = { ...newBlockBase, type: 'image', data_url: '', caption: '' };
        break;
      case 'table':
        newBlock = { ...newBlockBase, type: 'table', headers: ['Column 1', 'Column 2'], rows: [['', '']] };
        break;
      default:
        return;
    }

    onChange([...blocks, newBlock]);
    setShowMenu(false);
  };

  const updateBlock = (id: string, updatedBlock: ContentBlock) => {
    onChange(blocks.map(b => b.id === id ? updatedBlock : b));
  };

  const removeBlock = (id: string) => {
    onChange(blocks.filter(b => b.id !== id));
  };

  const moveBlock = (id: string, direction: 'up' | 'down') => {
    const index = blocks.findIndex(b => b.id === id);
    if (index < 0) return;
    if (direction === 'up' && index === 0) return;
    if (direction === 'down' && index === blocks.length - 1) return;

    const newBlocks = [...blocks];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    [newBlocks[index], newBlocks[targetIndex]] = [newBlocks[targetIndex], newBlocks[index]];
    onChange(newBlocks);
  };

  return (
    <div className="space-y-4">
      {blocks.map((block, index) => (
        <BlockRenderer
          key={block.id}
          block={block}
          onChange={(updated) => updateBlock(block.id, updated)}
          onRemove={() => removeBlock(block.id)}
          onMoveUp={() => moveBlock(block.id, 'up')}
          onMoveDown={() => moveBlock(block.id, 'down')}
          isFirst={index === 0}
          isLast={index === blocks.length - 1}
        />
      ))}

      <div className="relative mt-6">
        {showMenu ? (
          <div className="absolute bottom-full mb-2 left-0 w-64 bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden z-10">
            <div className="p-2 grid grid-cols-2 gap-1">
              <button onClick={() => addBlock('heading')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">Heading</button>
              <button onClick={() => addBlock('paragraph')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">Paragraph</button>
              <button onClick={() => addBlock('list')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">List</button>
              <button onClick={() => addBlock('incident_example')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">Incident Example</button>
              <button onClick={() => addBlock('description_box')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">Description Box</button>
              <button onClick={() => addBlock('code')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">Code / SQL</button>
              <button onClick={() => addBlock('image')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">Image</button>
              <button onClick={() => addBlock('table')} className="text-left px-3 py-2 text-sm hover:bg-gray-100 rounded">Table</button>
            </div>
          </div>
        ) : null}
        
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="flex items-center justify-center w-full py-4 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:text-blue-600 hover:border-blue-400 hover:bg-blue-50 transition-colors"
        >
          <PlusCircle className="w-5 h-5 mr-2" />
          Add Content Block
        </button>
      </div>
    </div>
  );
}
