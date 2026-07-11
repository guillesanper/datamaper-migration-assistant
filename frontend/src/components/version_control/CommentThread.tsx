// src/components/version_control/CommentThread.tsx
import React, { useState, useMemo } from 'react';
import {
  MessageSquare,
  Reply,
  Smile,
  Trash2,
  Edit,
  Send,
  User as UserIcon,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Comment, Reaction } from '../../types/version_control_types';
import { buildCommentTree, formatCommentDate } from '../../utils/version_control/commentUtils';
import { Button } from '../ui/button';
import styles from '../../styles/version_control/comment-thread.module.css';

interface CommentThreadProps {
  comments: Comment[];
  currentUserId?: string;
  onAddComment?: (content: string, parentId?: string) => Promise<void> | Promise<boolean>;
  onEditComment?: (commentId: string, content: string) => Promise<void> | Promise<boolean>;
  onDeleteComment?: (commentId: string) => Promise<void> | Promise<boolean>;
  onAddReaction?: (commentId: string, emoji: string) => Promise<void> | Promise<boolean>;
  onRemoveReaction?: (commentId: string, emoji: string) => Promise<void> | Promise<boolean>;
  placeholder?: string;
  maxDepth?: number;
  className?: string;
}

export const CommentThread: React.FC<CommentThreadProps> = ({
  comments,
  currentUserId,
  onAddComment,
  onEditComment,
  onDeleteComment,
  onAddReaction,
  onRemoveReaction,
  placeholder,
  maxDepth = 3,
  className = ''
}) => {
  const { t } = useTranslation(['version_control', 'common']);
  const [replyToId, setReplyToId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [newCommentContent, setNewCommentContent] = useState('');
  const [editContent, setEditContent] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const commentTree: Comment[] = useMemo(() => {
    return buildCommentTree(comments);
  }, [comments]);

  const handleSubmitComment = async (e: React.FormEvent, parentId?: string) => {
    e.preventDefault();
    if (!newCommentContent.trim() || !onAddComment || submitting) return;

    setSubmitting(true);
    try {
      await onAddComment(newCommentContent, parentId);
      setNewCommentContent('');
      setReplyToId(null);
    } catch (error) {
      console.error('[CommentThread] Error submitting comment:', error);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEditSubmit = async (commentId: string) => {
    if (!editContent.trim() || !onEditComment || submitting) return;

    setSubmitting(true);
    try {
      await onEditComment(commentId, editContent);
      setEditingId(null);
      setEditContent('');
    } catch (error) {
      console.error('[CommentThread] Error editing comment:', error);
    } finally {
      setSubmitting(false);
    }
  };

  const handleReactionToggle = async (commentId: string, emoji: string) => {
    const comment = comments.find((c) => c.id === commentId);
    if (!comment || !currentUserId) return;

    const userReacted = comment.reactions?.some(
      (r) => r.emoji === emoji && r.user_id === currentUserId
    );

    try {
      if (userReacted && onRemoveReaction) {
        await onRemoveReaction(commentId, emoji);
      } else if (!userReacted && onAddReaction) {
        await onAddReaction(commentId, emoji);
      }
    } catch (error) {
      console.error('[CommentThread] Error toggling reaction:', error);
    }
  };

  const renderComment = (thread: Comment, depth: number = 0) => {
    const comment = thread;
    const isAuthor = comment.user_id === currentUserId;
    const isEditing = editingId === comment.id;
    const isReplying = replyToId === comment.id;
    const canReply = depth < maxDepth;

    const groups: Record<string, { emoji: string; count: number; userReacted: boolean }> = {};
    comment.reactions?.forEach((reaction: Reaction) => {
      if (!groups[reaction.emoji]) {
        groups[reaction.emoji] = {
          emoji: reaction.emoji,
          count: 0,
          userReacted: false
        };
      }
      groups[reaction.emoji].count++;
      if (reaction.user_id === currentUserId) {
        groups[reaction.emoji].userReacted = true;
      }
    });
    const reactionGroups = Object.values(groups);

    return (
      <div key={comment.id} className={styles.commentWrapper}>
        <div className={styles.comment}>
          <div className={styles.avatar}>
            <UserIcon size={20} />
          </div>

          <div className={styles.commentContent}>
            <div className={styles.commentHeader}>
              <div className={styles.commentMeta}>
                <span className={styles.username}>{comment.username}</span>
                <span className={styles.timestamp}>{formatCommentDate(comment.created_at)}</span>
                {comment.updated_at !== comment.created_at && (
                  <span className={styles.editedLabel}>{t('version_control:commentThread.edited')}</span>
                )}
              </div>

              {isAuthor && (
                <div className={styles.commentActions}>
                  {onEditComment && (
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingId(comment.id);
                        setEditContent(comment.content);
                      }}
                      title={t('version_control:commentThread.edit')}
                    >
                      <Edit size={14} />
                    </Button>
                  )}
                  {onDeleteComment && (
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      onClick={() => onDeleteComment(comment.id)}
                      title={t('version_control:commentThread.delete')}
                    >
                      <Trash2 size={14} />
                    </Button>
                  )}
                </div>
              )}
            </div>

            {isEditing ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleEditSubmit(comment.id);
                }}
                className={styles.editForm}
              >
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className={styles.textarea}
                  rows={3}
                  autoFocus
                />
                <div className={styles.formActions}>
                  <Button type="submit" size="sm" disabled={submitting}>
                    {t('common:actions.save')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEditingId(null);
                      setEditContent('');
                    }}
                  >
                    {t('common:actions.cancel')}
                  </Button>
                </div>
              </form>
            ) : (
              <>
                <div className={styles.commentBody}>
                  {comment.content.split(/(@\w+)/g).map((part: string, i: number) =>
                    part.startsWith('@') ? (
                      <span key={i} className={styles.mention}>
                        {part}
                      </span>
                    ) : (
                      <span key={i}>{part}</span>
                    )
                  )}
                </div>

                {reactionGroups.length > 0 && (
                  <div className={styles.reactions}>
                    {reactionGroups.map((group) => (
                      <button
                        key={group.emoji}
                        className={`${styles.reactionButton} ${
                          group.userReacted ? styles.reactionActive : ''
                        }`}
                        onClick={() => handleReactionToggle(comment.id, group.emoji)}
                      >
                        <span className={styles.reactionEmoji}>{group.emoji}</span>
                        <span className={styles.reactionCount}>{group.count}</span>
                      </button>
                    ))}
                    {onAddReaction && (
                      <button
                        className={styles.addReactionButton}
                        onClick={() => handleReactionToggle(comment.id, '👍')}
                        title={t('version_control:commentThread.react')}
                      >
                        <Smile size={14} />
                      </button>
                    )}
                  </div>
                )}

                <div className={styles.commentFooter}>
                  {canReply && onAddComment && (
                    <button
                      className={styles.replyButton}
                      onClick={() => setReplyToId(comment.id)}
                    >
                      <Reply size={14} />
                      {t('version_control:commentThread.reply')}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {isReplying && onAddComment && (
          <form
            onSubmit={(e) => handleSubmitComment(e, comment.id)}
            className={styles.replyForm}
          >
            <textarea
              value={newCommentContent}
              onChange={(e) => setNewCommentContent(e.target.value)}
              placeholder={t('version_control:commentThread.replyTo', { username: comment.username })}
              className={styles.textarea}
              rows={2}
              autoFocus
            />
            <div className={styles.formActions}>
              <Button type="submit" size="sm" disabled={submitting}>
                <Send size={14} />
                {t('version_control:commentThread.send')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setReplyToId(null);
                  setNewCommentContent('');
                }}
              >
                {t('common:actions.cancel')}
              </Button>
            </div>
          </form>
        )}

        {thread.replies && thread.replies.length > 0 && (
          <div className={styles.replies}>
            {thread.replies.map((reply) => renderComment(reply, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={`${styles.container} ${className}`}>
      {onAddComment && !replyToId && (
        <form onSubmit={(e) => handleSubmitComment(e)} className={styles.newCommentForm}>
          <div className={styles.avatar}>
            <UserIcon size={20} />
          </div>
          <div className={styles.formContainer}>
            <textarea
              value={newCommentContent}
              onChange={(e) => setNewCommentContent(e.target.value)}
              placeholder={placeholder || t('version_control:commentThread.placeholder')}
              className={styles.textarea}
              rows={3}
            />
            <div className={styles.formActions}>
              <Button type="submit" size="sm" disabled={submitting || !newCommentContent.trim()}>
                <Send size={14} />
                {t('version_control:commentThread.submit')}
              </Button>
            </div>
          </div>
        </form>
      )}

      {commentTree.length > 0 ? (
        <div className={styles.commentList}>
          {commentTree.map((thread) => renderComment(thread, 0))}
        </div>
      ) : (
        <div className={styles.emptyState}>
          <MessageSquare size={48} />
          <p>{t('version_control:commentThread.empty')}</p>
          <p className={styles.emptyHint}>{t('version_control:commentThread.emptyHint')}</p>
        </div>
      )}
    </div>
  );
};
