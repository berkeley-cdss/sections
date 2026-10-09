import { useCallback, useContext } from "react";
import COURSE_BASE from "./coursePath";
import post from "./post";
import MessageContext from "./MessageContext";

// The server's JSON response for each API method varies, so callers type it.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function useAPI(method: string, callback?: ((data: any) => unknown) | null) {
  const { pushMessage } = useContext(MessageContext);

  return useCallback(
    async (args: { [key: string]: unknown } = {}) => {
      try {
        const resp = await post(`${COURSE_BASE}/api/${method}`, args, true);
        if (resp.success) {
          if (callback) {
            callback(resp.data);
          }
        } else {
          pushMessage(resp.message ?? "Unknown error.");
        }
      } catch (e) {
        console.error(e);
        pushMessage("Something went wrong.");
      }
    },
    [method, callback, pushMessage]
  );
}
