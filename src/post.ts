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
  if (skipTimeout) {
    return promise.then((resp) => resp.json());
  }
  return timeoutPromise(10000, promise).then((resp) => resp.json());
}
