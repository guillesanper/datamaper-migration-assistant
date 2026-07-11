// src/hooks/version_control/useComments.ts

import { useState, useCallback, useEffect } from 'react';
import { commentsService } from '@/services/version_control';
import type { Comment, CommentFilters } from '@/types/comments_types';
import { buildCommentTree } from '@/utils/version_control/commentUtils';

/**
 * Hook para gestión de comentarios de una entidad
 * REUTILIZA: Patrón de hooks del proyecto
 */
export const useComments = (entityId: string, entityType: string, projectId: string = '') => {
  const [comments, setComments] = useState<Comment[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Carga los comentarios
   */
  const loadComments = useCallback(async (filters?: CommentFilters) => {
    setLoading(true);
    setError(null);

    try {
      const data = await commentsService.getComments(entityId, entityType, filters);
      // Construir árbol de comentarios
      const tree = buildCommentTree(data);
      setComments(tree);

      // Contar no leídos
      const unread = data.filter(c => !c.is_read).length;
      setUnreadCount(unread);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al cargar comentarios');
      console.error('[useComments] Load error:', err);
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType]);

  /**
   * Añade un nuevo comentario
   */
  const addComment = useCallback(async (
    content: string,
    parentId?: string
  ): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      const newComment = await commentsService.addComment({
        entity_id: entityId,
        entity_type: entityType,
        project_id: projectId,
        content,
        parent_id: parentId
      });

      // Agregar localmente (optimistic update)
      if (parentId) {
        // Es un reply, actualizar el parent
        setComments(prev => {
          const updated = [...prev];
          const parent = findCommentById(updated, parentId);
          if (parent) {
            parent.replies = parent.replies || [];
            parent.replies.push(newComment);
          }
          return updated;
        });
      } else {
        // Es un comentario raíz
        setComments(prev => [newComment, ...prev]);
      }

      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al añadir comentario');
      console.error('[useComments] Add error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType]);

  /**
   * Edita un comentario
   */
  const editComment = useCallback(async (
    commentId: string,
    content: string
  ): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await commentsService.editComment(commentId, content);

      // Actualizar localmente
      setComments(prev => {
        const updatedComments = [...prev];
        const comment = findCommentById(updatedComments, commentId);
        if (comment) {
          comment.content = content;
          comment.is_edited = true;
          comment.updated_at = new Date().toISOString();
        }
        return updatedComments;
      });

      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al editar comentario');
      console.error('[useComments] Edit error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Elimina un comentario
   */
  const deleteComment = useCallback(async (commentId: string): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await commentsService.deleteComment(commentId);

      // Remover localmente
      setComments(prev => removeCommentFromTree(prev, commentId));

      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al eliminar comentario');
      console.error('[useComments] Delete error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Resuelve/no resuelve un comentario
   */
  const resolveComment = useCallback(async (
    commentId: string,
    resolved: boolean
  ): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await commentsService.resolveComment(commentId, resolved, projectId);

      // Actualizar localmente
      setComments(prev => {
        const updated = [...prev];
        const comment = findCommentById(updated, commentId);
        if (comment) {
          comment.is_resolved = resolved;
          if (resolved) {
            comment.resolved_at = new Date().toISOString();
          } else {
            comment.resolved_at = undefined;
            comment.resolved_by = undefined;
          }
        }
        return updated;
      });

      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al resolver comentario');
      console.error('[useComments] Resolve error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Añade una reacción
   */
  const addReaction = useCallback(async (
    commentId: string,
    emoji: string
  ): Promise<boolean> => {
    try {
      await commentsService.addReaction(commentId, emoji);

      // Actualizar localmente
      setComments(prev => {
        const updated = [...prev];
        const comment = findCommentById(updated, commentId);
        if (comment) {
          comment.reactions = comment.reactions || [];
          comment.reactions.push({
            emoji,
            user_id: 'current', // Se actualizará desde el servidor
            username: 'Tú',
            created_at: new Date().toISOString()
          });
        }
        return updated;
      });

      return true;
    } catch (err: unknown) {
      console.error('[useComments] Add reaction error:', err);
      return false;
    }
  }, []);

  /**
   * Remueve una reacción
   */
  const removeReaction = useCallback(async (
    commentId: string,
    emoji: string
  ): Promise<boolean> => {
    try {
      await commentsService.removeReaction(commentId, emoji);

      // Actualizar localmente
      setComments(prev => {
        const updated = [...prev];
        const comment = findCommentById(updated, commentId);
        if (comment && comment.reactions) {
          comment.reactions = comment.reactions.filter(
            r => !(r.emoji === emoji && r.user_id === 'current')
          );
        }
        return updated;
      });

      return true;
    } catch (err: unknown) {
      console.error('[useComments] Remove reaction error:', err);
      return false;
    }
  }, []);

  /**
   * Marca comentarios como leídos
   */
  const markAsRead = useCallback(async (commentIds: string[]): Promise<boolean> => {
    try {
      await commentsService.markAsRead(commentIds);

      // Actualizar contador
      setUnreadCount(prev => Math.max(0, prev - commentIds.length));

      return true;
    } catch (err: unknown) {
      console.error('[useComments] Mark as read error:', err);
      return false;
    }
  }, []);

  /**
   * Limpia el error
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Cargar comentarios al montar
  useEffect(() => {
    if (entityId && entityType) {
      loadComments();
    }
  }, [entityId, entityType, loadComments]);

  return {
    comments,
    unreadCount,
    loading,
    error,
    loadComments,
    addComment,
    editComment,
    deleteComment,
    resolveComment,
    addReaction,
    removeReaction,
    markAsRead,
    clearError
  };
};

// Helper functions
function findCommentById(comments: Comment[], commentId: string): Comment | null {
  for (const comment of comments) {
    if (comment.id === commentId) {
      return comment;
    }
    if (comment.replies) {
      const found = findCommentById(comment.replies, commentId);
      if (found) return found;
    }
  }
  return null;
}

function removeCommentFromTree(comments: Comment[], commentId: string): Comment[] {
  return comments.filter(c => {
    if (c.id === commentId) return false;
    if (c.replies) {
      c.replies = removeCommentFromTree(c.replies, commentId);
    }
    return true;
  });
}

export default useComments;
