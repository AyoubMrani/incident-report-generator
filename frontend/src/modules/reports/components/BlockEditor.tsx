import React, { useState } from 'react';
import { ContentBlock, BlockType } from '../../../types';
import { BlockRenderer } from './BlockRenderer';
import { PlusCircle, FileJson, FileText } from 'lucide-react';
import { NTT_BLUE } from '../../../ui/Brand';

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
        newBlock = { ...newBlockBase, type: 'list', ordered: false, items: [''], label: '' };
        break;
      case 'incident_example':
        newBlock = { ...newBlockBase, type: 'incident_example', incident_id: '', link: '' };
        break;
      case 'code':
        newBlock = { ...newBlockBase, type: 'code', items: [] };
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
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="border-app-strong text-app-muted hover:text-[var(--ntt-blue)] flex w-full items-center justify-center rounded-lg border-2 border-dashed py-4 transition hover:bg-app-hover"
          style={{ ['--ntt-blue' as any]: NTT_BLUE }}
        >
          <PlusCircle className="mr-2 w-5 h-5" />
          Add Content Block
        </button>

        {showMenu ? (
          <div className="bg-app-elevated border-app absolute top-full left-0 z-10 mt-2 w-64 overflow-hidden rounded-lg border shadow-xl">
            <div className="grid grid-cols-2 gap-1 p-2">
              <button onClick={() => addBlock('heading')} className="hover:bg-app-hover text-app rounded px-3 py-2 text-left text-sm transition">Heading</button>
              <button onClick={() => addBlock('paragraph')} className="hover:bg-app-hover text-app rounded px-3 py-2 text-left text-sm transition">Paragraph</button>
              <button onClick={() => addBlock('list')} className="hover:bg-app-hover text-app rounded px-3 py-2 text-left text-sm transition">List / Steps</button>
              <button onClick={() => addBlock('incident_example')} className="hover:bg-app-hover text-app rounded px-3 py-2 text-left text-sm transition">Incident Example</button>
              <button onClick={() => addBlock('code')} className="hover:bg-app-hover text-app rounded px-3 py-2 text-left text-sm transition">Code / SQL</button>
              <button onClick={() => addBlock('image')} className="hover:bg-app-hover text-app rounded px-3 py-2 text-left text-sm transition">Image</button>
              <button onClick={() => addBlock('table')} className="hover:bg-app-hover text-app rounded px-3 py-2 text-left text-sm transition">Table</button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
