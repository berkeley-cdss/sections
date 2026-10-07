// @flow strict

import { useCallback, useContext } from "react";
import COURSE_BASE from "./coursePath";
import post from "./post";
import MessageContext from "./MessageContext";

export default function useAPI(method: string, callback: ?(any) => mixed) {
  const { pushMessage } = useContext(MessageContext);

  return useCallback(
    async (args: { [key: string]: any } = {}) => {
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
