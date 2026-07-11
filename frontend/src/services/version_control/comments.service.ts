// src/services/version_control/comments.service.ts

import { apiService } from '../api.service';
import type {
  Comment,
  CommentResponse,
  CreateCommentRequest,
  EditCommentRequest,
  ResolveCommentRequest,
  AddReactionRequest,
  CommentFilters
} from '@/types/comments_types';
import { extractMentions } from '@/utils/version_control/commentUtils';

/**
 * Servicio para gestión de comentarios
 * REUTILIZA: apiService existente
 */
class CommentsService {
  private readonly BASE_PATH = '/api/comments';

  /**
   * Añade un nuevo comentario
   */
  async addComment(data: CreateCommentRequest): Promise<Comment> {
    try {
      // Extraer menciones automáticamente
      const mentions = extractMentions(data.content);

      const response = await apiService.post<CommentResponse>(this.BASE_PATH, {
        ...data,
        mentions
      });

      if (!response.success || !response.data?.comment) {
        throw new Error(response.message || 'Error al crear comentario');
      }

      return response.data.comment;
    } catch (error: unknown) {
      console.error('[CommentsService] Error adding comment:', error);
      throw error;
    }
  }

  /**
   * Edita un comentario existente
   */
  async editComment(commentId: string, content: string): Promise<Comment> {
    try {
      const mentions = extractMentions(content);

      const response = await apiService.put<CommentResponse>(
        `${this.BASE_PATH}/${commentId}`,
        { content, mentions } as EditCommentRequest & { mentions: string[] }
      );

      if (!response.success || !response.data?.comment) {
        throw new Error(response.message || 'Error al editar comentario');
      }

      return response.data.comment;
    } catch (error: unknown) {
      console.error('[CommentsService] Error editing comment:', error);
      throw error;
    }
  }

  /**
   * Elimina un comentario
   */
  async deleteComment(commentId: string): Promise<void> {
    try {
      const response = await apiService.delete<CommentResponse>(
        `${this.BASE_PATH}/${commentId}`
      );

      if (!response.success) {
        throw new Error(response.message || 'Error al eliminar comentario');
      }
    } catch (error: unknown) {
      console.error('[CommentsService] Error deleting comment:', error);
      throw error;
    }
  }

  /**
   * Marca un comentario como resuelto/no resuelto
   */
  async resolveComment(commentId: string, resolved: boolean, projectId: string): Promise<Comment> {
    try {
      const response = await apiService.patch<CommentResponse>(
        `${this.BASE_PATH}/${commentId}/resolve`,
        { resolved, project_id: projectId } as ResolveCommentRequest
      );

      if (!response.success || !response.data?.comment) {
        throw new Error(response.message || 'Error al resolver comentario');
      }

      return response.data.comment;
    } catch (error: unknown) {
      console.error('[CommentsService] Error resolving comment:', error);
      throw error;
    }
  }

  /**
   * Añade una reacción emoji a un comentario
   */
  async addReaction(commentId: string, emoji: string): Promise<void> {
    try {
      const response = await apiService.post<CommentResponse>(
        `${this.BASE_PATH}/${commentId}/reactions`,
        { emoji } as AddReactionRequest
      );

      if (!response.success) {
        throw new Error(response.message || 'Error al añadir reacción');
      }
    } catch (error: unknown) {
      console.error('[CommentsService] Error adding reaction:', error);
      throw error;
    }
  }

  /**
   * Elimina una reacción emoji de un comentario
   */
  async removeReaction(commentId: string, emoji: string): Promise<void> {
    try {
      const response = await apiService.delete<CommentResponse>(
        `${this.BASE_PATH}/${commentId}/reactions/${encodeURIComponent(emoji)}`
      );

      if (!response.success) {
        throw new Error(response.message || 'Error al eliminar reacción');
      }
    } catch (error: unknown) {
      console.error('[CommentsService] Error removing reaction:', error);
      throw error;
    }
  }

  /**
   * Obtiene comentarios de una entidad
   */
  async getComments(entityId: string, entityType: string, filters?: CommentFilters): Promise<Comment[]> {
    try {
      const params = new URLSearchParams();
      params.append('entity_id', entityId);
      params.append('entity_type', entityType);

      if (filters?.user_id) params.append('user_id', filters.user_id);
      if (filters?.include_resolved !== undefined) {
        params.append('include_resolved', filters.include_resolved.toString());
      }
      if (filters?.include_replies !== undefined) {
        params.append('include_replies', filters.include_replies.toString());
      }
      if (filters?.only_unread) params.append('only_unread', 'true');
      if (filters?.search_term) params.append('search', filters.search_term);

      const response = await apiService.get<CommentResponse>(
        `${this.BASE_PATH}?${params.toString()}`
      );

      if (!response.success || !response.data?.comments) {
        throw new Error(response.message || 'Error al obtener comentarios');
      }

      return response.data.comments;
    } catch (error: unknown) {
      console.error('[CommentsService] Error getting comments:', error);
      throw error;
    }
  }

  /**
   * Marca comentarios como leídos
   */
  async markAsRead(commentIds: string[]): Promise<void> {
    try {
      const response = await apiService.post<CommentResponse>(
        `${this.BASE_PATH}/mark-read`,
        { comment_ids: commentIds }
      );

      if (!response.success) {
        throw new Error(response.message || 'Error al marcar como leído');
      }
    } catch (error: unknown) {
      console.error('[CommentsService] Error marking as read:', error);
      throw error;
    }
  }

  /**
   * Obtiene el contador de comentarios no leídos de un proyecto
   */
  async getUnreadCount(projectId: string): Promise<number> {
    try {
      const response = await apiService.get<CommentResponse>(
        `${this.BASE_PATH}/unread-count?project_id=${projectId}`
      );

      if (!response.success || response.data?.unread_count === undefined) {
        throw new Error(response.message || 'Error al obtener contador');
      }

      return response.data.unread_count;
    } catch (error: unknown) {
      console.error('[CommentsService] Error getting unread count:', error);
      throw error;
    }
  }

  /**
   * Obtiene comentarios de un proyecto completo
   */
  async getProjectComments(projectId: string, filters?: CommentFilters): Promise<Comment[]> {
    try {
      const params = new URLSearchParams();
      params.append('project_id', projectId);

      if (filters?.entity_type) params.append('entity_type', filters.entity_type);
      if (filters?.user_id) params.append('user_id', filters.user_id);
      if (filters?.include_resolved !== undefined) {
        params.append('include_resolved', filters.include_resolved.toString());
      }
      if (filters?.only_unread) params.append('only_unread', 'true');

      const response = await apiService.get<CommentResponse>(
        `${this.BASE_PATH}/project?${params.toString()}`
      );

      if (!response.success || !response.data?.comments) {
        throw new Error(response.message || 'Error al obtener comentarios del proyecto');
      }

      return response.data.comments;
    } catch (error: unknown) {
      console.error('[CommentsService] Error getting project comments:', error);
      throw error;
    }
  }
}

// Exportar instancia singleton
export const commentsService = new CommentsService();
export default CommentsService;
