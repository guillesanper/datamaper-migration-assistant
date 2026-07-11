// src/types/comments_types.ts

/**
 * Comentario
 */
export interface Comment {
  id: string;
  entity_id: string;
  entity_type: string;
  project_id: string;
  user_id: string;
  username: string;
  user_email?: string;
  user_avatar?: string;
  parent_id?: string;
  content: string;
  created_at: string;
  updated_at?: string;
  is_edited: boolean;
  is_resolved: boolean;
  resolved_by?: string;
  resolved_by_name?: string;
  resolved_at?: string;
  mentions?: string[]; // user_ids mencionados
  reactions: Reaction[];
  replies?: Comment[]; // Comentarios anidados
  is_read: boolean;
}

/**
 * Reacción a un comentario
 */
export interface Reaction {
  emoji: string;
  user_id: string;
  username: string;
  created_at: string;
}

/**
 * Request para crear comentario
 */
export interface CreateCommentRequest {
  entity_id: string;
  entity_type: string;
  project_id: string;
  content: string;
  parent_id?: string;
  mentions?: string[];
}

/**
 * Request para editar comentario
 */
export interface EditCommentRequest {
  content: string;
}

/**
 * Request para resolver comentario
 */
export interface ResolveCommentRequest {
  resolved: boolean;
  project_id: string;
}

/**
 * Request para añadir reacción
 */
export interface AddReactionRequest {
  emoji: string;
}

/**
 * Filtros para comentarios
 */
export interface CommentFilters {
  entity_id?: string;
  entity_type?: string;
  user_id?: string;
  include_resolved?: boolean;
  include_replies?: boolean;
  only_unread?: boolean;
  search_term?: string;
}

/**
 * Response de operaciones de comentarios
 */
export interface CommentResponse {
  success: boolean;
  message?: string;
  data?: {
    comment?: Comment;
    comments?: Comment[];
    total?: number;
    unread_count?: number;
  };
}

/**
 * Thread de comentarios (agrupados)
 */
export interface CommentThread {
  parent: Comment;
  replies: Comment[];
  total_replies: number;
  unread_replies: number;
}

/**
 * Estadísticas de comentarios
 */
export interface CommentStats {
  total_comments: number;
  unread_count: number;
  resolved_count: number;
  active_threads: number;
}

/**
 * Usuario escribiendo (typing indicator)
 */
export interface TypingUser {
  user_id: string;
  username: string;
  entity_id: string;
  entity_type: string;
  started_at: string;
}
