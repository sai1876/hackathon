export interface PollingLifecycleCallbacks<T> {
  onSuccess: (data: T) => void;
  onError: (error: string) => void;
}

export function calculateBackoff(failures: number, normalIntervalMs: number = 3000): number {
  if (failures <= 0) return normalIntervalMs;
  if (failures === 1) return 5000;
  if (failures === 2) return 10000;
  if (failures === 3) return 20000;
  return 30000; // Cap at 30 seconds
}

export class PollingLifecycleManager<T> {
  public consecutiveFailures = 0;
  public inFlight = false;
  public timer: ReturnType<typeof setTimeout> | null = null;
  public abortController: AbortController | null = null;
  public isCancelled = false;
  private fetcher: (signal: AbortSignal) => Promise<T>;
  private callbacks: PollingLifecycleCallbacks<T>;
  public normalIntervalMs: number;
  public defaultErrorMessage: string;

  constructor(
    fetcher: (signal: AbortSignal) => Promise<T>,
    callbacks: PollingLifecycleCallbacks<T>,
    normalIntervalMs = 3000,
    defaultErrorMessage = "Backend connection unavailable — data may be stale"
  ) {
    this.fetcher = fetcher;
    this.callbacks = callbacks;
    this.normalIntervalMs = normalIntervalMs;
    this.defaultErrorMessage = defaultErrorMessage;
  }

  public async poll(isManual = false): Promise<void> {
    if (this.isCancelled) return;
    if (this.inFlight && !isManual) return; // Prevent overlapping fetches

    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    if (this.abortController) {
      this.abortController.abort();
    }

    const controller = new AbortController();
    this.abortController = controller;
    this.inFlight = true;

    try {
      const result = await this.fetcher(controller.signal);
      if (!controller.signal.aborted && !this.isCancelled) {
        this.consecutiveFailures = 0; // Success resets backoff
        this.callbacks.onSuccess(result);
      }
    } catch (err) {
      if (!controller.signal.aborted && !this.isCancelled) {
        this.consecutiveFailures += 1; // Increment failures on error
        const msg = err instanceof Error ? err.message : this.defaultErrorMessage;
        this.callbacks.onError(msg);
      }
    } finally {
      if (!controller.signal.aborted && !this.isCancelled) {
        this.inFlight = false;
        const delay = calculateBackoff(this.consecutiveFailures, this.normalIntervalMs);
        this.timer = setTimeout(() => {
          void this.poll();
        }, delay);
      }
    }
  }

  public cancel(): void {
    this.isCancelled = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.inFlight = false;
  }
}
