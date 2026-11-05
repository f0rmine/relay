export interface User {
  id: string;
  username: string;
  email?: string;
  display_name: string;
  avatar_url?: string | null;
  created_at?: string;
  last_seen_at?: string | null;
  is_online?: boolean;
}

export interface Attachment {
  id: string;
  message_id?: string | null;
  uploader_id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  public_url: string;
  thumb_w?: number | null;
  thumb_h?: number | null;
  thumb_size?: number | null;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  client_message_id?: string | null;
  text?: string | null;
  undecryptable?: boolean;
  created_at: string;
  updated_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
  deleted_by_id?: string | null;
  attachments: Attachment[];
  read_by: string[];
  request_id?: string;
  delivery_state?: 'queued' | 'sending' | 'failed';
  reactions?: Array<{ emoji: string; user_ids: string[] }>;
  reply_to?: { id: string; text?: string | null; sender_id: string; undecryptable?: boolean } | null;
}

export interface Conversation {
  id: string;
  kind: string;
  title?: string | null;
  avatar_url?: string | null;
  first_unread_id?: string | null;
  is_admin?: boolean;
  admin_ids?: string[];
  pinned_message_id?: string | null;
  participants: User[];
  latest_message?: Message | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionInfo {
  jti?: string | null;
  short_id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
  legacy: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}
