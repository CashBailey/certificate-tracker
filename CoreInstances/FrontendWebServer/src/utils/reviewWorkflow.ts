export type DocumentLoadState = 'loading' | 'ready' | 'error';

export function canApproveReview(
  documentState: DocumentLoadState,
  submitting: boolean,
): boolean {
  return documentState === 'ready' && !submitting;
}
