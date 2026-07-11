// src/components/team/CommentsSection.tsx
import React, { useState, useEffect } from 'react';
import { MessageSquare, Send, Loader2, CheckCircle, Circle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { type TFunction } from 'i18next';
import { Button } from '../ui/button';
import { commentsService } from '../../services/version_control/comments.service';
import type { Comment } from '../../types/comments_types';
import { useAuth } from '../../providers/AuthProvider';
import { toast } from '../../utils/toast';

interface CommentsSectionProps {
  entityId: string;
  entityType: string;
  projectId: string;
}

function formatTime(dateString: string, t: TFunction<['team', 'common']>): string {
  const date = new Date(dateString);
  const diff = Math.floor((Date.now() - date.getTime()) / 60000);
  const hours = Math.floor(diff / 60);
  const days = Math.floor(hours / 24);
  if (diff < 1) return t('common:time.now');
  if (diff < 60) return t('common:time.minutes', { count: diff });
  if (hours < 24) return t('common:time.hours', { count: hours });
  return t('common:time.days', { count: days });
}

export const CommentsSection: React.FC<CommentsSectionProps> = ({ entityId, entityType, projectId }) => {
  const { t } = useTranslation<['team', 'common']>(['team', 'common']);
  const { user } = useAuth();
  const [comments, setComments] = useState<Comment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newComment, setNewComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [showResolved, setShowResolved] = useState(false);

  useEffect(() => {
    loadComments();
  }, [entityId, entityType, showResolved]);

  const loadComments = async () => {
    try {
      setIsLoading(true);
      const data = await commentsService.getComments(entityId, entityType, {
        include_resolved: showResolved,
        include_replies: true
      });
      setComments(data);
    } catch (error: unknown) {
      console.error('Error loading comments:', error);
      toast.error(t('comments.errors.load'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!newComment.trim()) return;

    try {
      setIsSubmitting(true);
      await commentsService.addComment({
        entity_id: entityId,
        entity_type: entityType,
        project_id: projectId,
        content: newComment.trim(),
        parent_id: replyingTo || undefined
      });

      setNewComment('');
      setReplyingTo(null);
      toast.success(t('comments.success.added'));
      await loadComments();
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : t('comments.errors.add'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (commentId: string) => {
    if (!window.confirm(t('comments.deleteConfirm'))) return;

    try {
      await commentsService.deleteComment(commentId);
      toast.success(t('comments.success.deleted'));
      await loadComments();
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : t('comments.errors.delete'));
    }
  };

  const handleToggleResolve = async (commentId: string, currentlyResolved: boolean) => {
    try {
      await commentsService.resolveComment(commentId, !currentlyResolved, projectId);
      toast.success(currentlyResolved ? t('comments.success.reopened') : t('comments.success.resolved'));
      await loadComments();
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : t('comments.errors.toggleResolve'));
    }
  };

  const renderComment = (comment: Comment, isReply: boolean = false) => {
    const isOwn = comment.user_id === user?.id;
    const userName = comment.username || comment.user_email?.split('@')[0] || 'Usuario';

    return (
      <div
        key={comment.id}
        className={`${isReply ? 'ml-12 mt-2' : 'mt-3'} ${
          comment.is_resolved ? 'opacity-60' : ''
        }`}
      >
        <div className="flex gap-3">
          {/* Avatar */}
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center font-semibold text-sm flex-shrink-0">
            {userName[0].toUpperCase()}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="bg-muted/50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-sm">{userName}</span>
                <span className="text-xs text-muted-foreground">
                  {formatTime(comment.created_at, t)}
                </span>
              </div>
              <p className="text-sm whitespace-pre-wrap break-words">{comment.content}</p>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 mt-1 text-xs">
              {!isReply && (
                <button
                  onClick={() => setReplyingTo(comment.id)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {t('comments.reply')}
                </button>
              )}

              {isOwn && (
                <button
                  onClick={() => handleDelete(comment.id)}
                  className="text-destructive hover:text-destructive/80"
                >
                  {t('comments.delete')}
                </button>
              )}

              {!isReply && (
                <button
                  onClick={() => handleToggleResolve(comment.id, comment.is_resolved)}
                  className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
                >
                  {comment.is_resolved ? (
                    <>
                      <CheckCircle className="w-3 h-3" />
                      {t('comments.resolved')}
                    </>
                  ) : (
                    <>
                      <Circle className="w-3 h-3" />
                      {t('comments.resolve')}
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Replies */}
            {comment.replies && comment.replies.length > 0 && (
              <div className="mt-2">
                {comment.replies.map(reply => renderComment(reply, true))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const topLevelComments = comments.filter(c => !c.parent_id);
  const unresolvedCount = topLevelComments.filter(c => !c.is_resolved).length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">{t('comments.title')}</h3>
          <p className="text-sm text-muted-foreground">
            {t('comments.count', { count: topLevelComments.length })}
            {unresolvedCount > 0 && ` ${t('comments.unresolvedCount', { count: unresolvedCount })}`}
          </p>
        </div>
        <button
          onClick={() => setShowResolved(!showResolved)}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          {showResolved ? t('comments.hideResolved') : t('comments.showResolved')}
        </button>
      </div>

      {/* New Comment Form */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center font-semibold text-sm flex-shrink-0">
          {user?.email?.[0].toUpperCase()}
        </div>
        <div className="flex-1 flex gap-2">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder={replyingTo ? t('comments.replyPlaceholder') : t('comments.placeholder')}
            className="flex-1 px-3 py-2 rounded-md border bg-background text-sm"
            disabled={isSubmitting}
          />
          <Button
            type="submit"
            size="sm"
            disabled={isSubmitting || !newComment.trim()}
          >
            {isSubmitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </form>

      {replyingTo && (
        <div className="ml-10 text-xs text-muted-foreground flex items-center gap-2">
          {t('comments.replyingTo')}
          <button
            onClick={() => setReplyingTo(null)}
            className="text-destructive hover:underline"
          >
            {t('common:actions.cancel')}
          </button>
        </div>
      )}

      {/* Comments List */}
      <div className="space-y-2">
        {topLevelComments.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <MessageSquare className="w-12 h-12 mx-auto mb-2 opacity-20" />
            <p>{t('comments.empty')}</p>
          </div>
        ) : (
          topLevelComments.map(comment => renderComment(comment))
        )}
      </div>
    </div>
  );
};
