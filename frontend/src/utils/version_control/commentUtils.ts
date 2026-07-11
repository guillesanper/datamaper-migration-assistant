// src/utils/version_control/commentUtils.ts

import type { Comment, CommentThread } from '@/types/comments_types';

/**
 * Construye un árbol de comentarios con replies anidados
 */
export const buildCommentTree = (comments: Comment[]): Comment[] => {
  const commentMap = new Map<string, Comment>();
  const rootComments: Comment[] = [];

  // Crear mapa de comentarios
  comments.forEach(comment => {
    commentMap.set(comment.id, { ...comment, replies: [] });
  });

  // Construir árbol
  comments.forEach(comment => {
    const commentWithReplies = commentMap.get(comment.id)!;

    if (comment.parent_id) {
      // Es un reply, añadirlo al parent
      const parent = commentMap.get(comment.parent_id);
      if (parent) {
        parent.replies = parent.replies || [];
        parent.replies.push(commentWithReplies);
      }
    } else {
      // Es un comentario raíz
      rootComments.push(commentWithReplies);
    }
  });

  // Ordenar replies por fecha
  const sortReplies = (comment: Comment) => {
    if (comment.replies && comment.replies.length > 0) {
      comment.replies.sort((a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
      comment.replies.forEach(sortReplies);
    }
  };

  rootComments.forEach(sortReplies);

  // Ordenar root comments por fecha (más recientes primero)
  return rootComments.sort((a, b) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
};

/**
 * Extrae menciones de un texto (@username)
 */
export const extractMentions = (content: string): string[] => {
  const regex = /@(\w+)/g;
  const matches = content.matchAll(regex);
  return Array.from(matches, m => m[1]);
};

/**
 * Reemplaza menciones con elementos clicables
 */
export const replaceMentionsWithLinks = (content: string): string => {
  return content.replace(/@(\w+)/g, '<span class="mention" data-user="$1">@$1</span>');
};

/**
 * Parse markdown básico (bold, italic, code)
 */
export const parseMarkdown = (content: string): string => {
  let parsed = content;

  // Code blocks ```code```
  parsed = parsed.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

  // Inline code `code`
  parsed = parsed.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Bold **text**
  parsed = parsed.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Italic *text*
  parsed = parsed.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Links [text](url)
  parsed = parsed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

  // Line breaks
  parsed = parsed.replace(/\n/g, '<br>');

  return parsed;
};

/**
 * Formatea el tiempo relativo de un comentario
 */
export const formatCommentTime = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 30) {
    return 'ahora';
  } else if (diffSecs < 60) {
    return 'hace un momento';
  } else if (diffMins < 60) {
    return `hace ${diffMins}m`;
  } else if (diffHours < 24) {
    return `hace ${diffHours}h`;
  } else if (diffDays < 7) {
    return `hace ${diffDays}d`;
  } else {
    return date.toLocaleDateString('es-ES', {
      day: 'numeric',
      month: 'short'
    });
  }
};

/**
 * Alias para formatCommentTime (para compatibilidad)
 */
export const formatCommentDate = formatCommentTime;

/**
 * Cuenta el total de replies en un comentario (recursivo)
 */
export const countTotalReplies = (comment: Comment): number => {
  if (!comment.replies || comment.replies.length === 0) {
    return 0;
  }

  let count = comment.replies.length;
  comment.replies.forEach(reply => {
    count += countTotalReplies(reply);
  });

  return count;
};

/**
 * Cuenta replies no leídos
 */
export const countUnreadReplies = (comment: Comment): number => {
  if (!comment.replies || comment.replies.length === 0) {
    return 0;
  }

  let count = comment.replies.filter(r => !r.is_read).length;
  comment.replies.forEach(reply => {
    count += countUnreadReplies(reply);
  });

  return count;
};

/**
 * Agrupa comentarios por thread
 */
export const groupCommentsIntoThreads = (comments: Comment[]): CommentThread[] => {
  const tree = buildCommentTree(comments);

  return tree.map(parent => ({
    parent,
    replies: parent.replies || [],
    total_replies: countTotalReplies(parent),
    unread_replies: countUnreadReplies(parent)
  }));
};

/**
 * Obtiene todos los IDs de comentarios en un thread (incluyendo replies)
 */
export const getThreadCommentIds = (comment: Comment): string[] => {
  const ids = [comment.id];

  if (comment.replies) {
    comment.replies.forEach(reply => {
      ids.push(...getThreadCommentIds(reply));
    });
  }

  return ids;
};

/**
 * Busca un comentario por ID en un árbol
 */
export const findCommentById = (comments: Comment[], commentId: string): Comment | null => {
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
};

/**
 * Valida el contenido de un comentario
 */
export const validateCommentContent = (content: string): { valid: boolean; error?: string } => {
  const trimmed = content.trim();

  if (trimmed.length === 0) {
    return { valid: false, error: 'El comentario no puede estar vacío' };
  }

  if (trimmed.length > 4000) {
    return { valid: false, error: 'El comentario es demasiado largo (máximo 4000 caracteres)' };
  }

  return { valid: true };
};

/**
 * Trunca el contenido de un comentario para preview
 */
export const truncateComment = (content: string, maxLength: number = 100): string => {
  if (content.length <= maxLength) {
    return content;
  }

  return content.substring(0, maxLength).trim() + '...';
};

/**
 * Obtiene el emoji más usado en reacciones
 */
export const getMostUsedEmoji = (comment: Comment): string | null => {
  if (!comment.reactions || comment.reactions.length === 0) {
    return null;
  }

  const emojiCount = new Map<string, number>();

  comment.reactions.forEach(reaction => {
    const count = emojiCount.get(reaction.emoji) || 0;
    emojiCount.set(reaction.emoji, count + 1);
  });

  let maxEmoji = null;
  let maxCount = 0;

  emojiCount.forEach((count, emoji) => {
    if (count > maxCount) {
      maxCount = count;
      maxEmoji = emoji;
    }
  });

  return maxEmoji;
};
