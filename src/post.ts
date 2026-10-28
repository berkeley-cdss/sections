type APIResponse = {
  success: boolean;
  data?: unknown;
  message?: string;
};

function timeoutPromise<T>(ms: number, promise: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error("promise timeout"));
    }, ms);
    promise.then(
      (res) => {
        clearTimeout(timeoutId);
        resolve(res);
      },
      (err) => {
        clearTimeout(timeoutId);
        reject(err);
      }
    );
  });
}

// A request that failed before the server could say why; its message is shown to the user.
export class RequestError extends Error {}

async function readResponse(resp: Response): Promise<APIResponse> {
  try {
    return await resp.json();
  } catch {
    // The server answers every API call with JSON, even errors, so this came
    // from in front of it, e.g. Cloud Run while it restarts.
    throw new RequestError(
      resp.status >= 502 && resp.status <= 504
        ? `Sections is temporarily unavailable (HTTP ${resp.status}). Wait a minute and try again.`
        : `Sections sent an unexpected response (HTTP ${resp.status}). Reload the page and try again.`
    );
  }
}

export default async function post(
  endpoint: string,
  data: unknown,
  skipTimeout?: boolean
): Promise<APIResponse> {
  const promise = fetch(endpoint, {
    method: "POST",
    cache: "no-cache",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
  let resp: Response;
  try {
    resp = await (skipTimeout ? promise : timeoutPromise(10000, promise));
  } catch {
    throw new RequestError(
      "Couldn't reach Sections. Check your internet connection and try again."
    );
  }
  return readResponse(resp);
}
