import { useCallback, useContext } from "react";
import COURSE_BASE from "./coursePath";
import post, { RequestError } from "./post";
import MessageContext from "./MessageContext";

// The server's JSON response for each API method varies, so callers type it.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function useAPI(method: string, callback?: ((data: any) => unknown) | null) {
  const { pushMessage } = useContext(MessageContext);

  return useCallback(
    async (args: { [key: string]: unknown } = {}) => {
      let resp;
      try {
        resp = await post(`${COURSE_BASE}/api/${method}`, args, true);
      } catch (e) {
        console.error(e);
        pushMessage(e instanceof RequestError ? e.message : "Something went wrong sending your request.");
        return;
      }
      if (!resp.success) {
        pushMessage(resp.message ?? "Unknown error.");
        return;
      }
      try {
        callback?.(resp.data);
      } catch (e) {
        // The server did its part; showing the result failed.
        console.error(e);
        pushMessage("Your request went through, but this page couldn't show the result. Reload the page.");
      }
    },
    [method, callback, pushMessage]
  );
}
