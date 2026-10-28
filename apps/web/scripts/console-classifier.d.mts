export type ConsoleEvent = {kind: string; text: string; url: string};
export type ConsoleScope = {scenario: string; failures: {url: string; status: number}[]};
export function classifyConsoleError(
  event: ConsoleEvent, scope?: ConsoleScope,
): {expected: boolean; scenario: string | null; category?: string | null};
export function withConsoleScope<T>(
  scopes: WeakMap<object, ConsoleScope>, page: object, scope: ConsoleScope,
  operation: () => Promise<T>,
): Promise<T>;
