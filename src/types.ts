export type BlockType = 
  | 'heading' 
  | 'paragraph' 
  | 'list' 
  | 'incident_example' 
  | 'description_box' 
  | 'code' 
  | 'image' 
  | 'table';

export interface BaseBlock {
  id: string;
  type: BlockType;
}

export interface HeadingBlock extends BaseBlock {
  type: 'heading';
  level: 1 | 2 | 3 | 4;
  content: string;
}

export interface ParagraphBlock extends BaseBlock {
  type: 'paragraph';
  content: string;
}

export interface ListBlock extends BaseBlock {
  type: 'list';
  ordered: boolean;
  items: string[];
}

export interface IncidentExampleBlock extends BaseBlock {
  type: 'incident_example';
  incident_id: string;
}

export interface DescriptionBoxBlock extends BaseBlock {
  type: 'description_box';
  label: string;
  items: string[];
}

export interface CodeBlock extends BaseBlock {
  type: 'code';
  language: string;
  content: string;
}

export interface ImageBlock extends BaseBlock {
  type: 'image';
  data_url: string;
  caption: string;
}

export interface TableBlock extends BaseBlock {
  type: 'table';
  headers: string[];
  rows: string[][];
}

export type ContentBlock = 
  | HeadingBlock 
  | ParagraphBlock 
  | ListBlock 
  | IncidentExampleBlock 
  | DescriptionBoxBlock 
  | CodeBlock 
  | ImageBlock 
  | TableBlock;

export interface ReportMetadata {
  incident_id: string;
  title: string;
  caller: string;
  category: string;
  subcategory: string;
  date: string;
  [key: string]: string;
}

export interface IncidentReport {
  metadata: ReportMetadata;
  blocks: ContentBlock[];
}

export interface StoredCategoryOption {
  id: string;
  label: string;
}

export interface StoredMetadataField {
  id: string;
  name: string;
  label: string;
  isPermanent?: boolean;
}
