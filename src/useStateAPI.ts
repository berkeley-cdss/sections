import { useCallback, useContext } from "react";
import type { State } from "./models";
import StateContext from "./StateContext";
import useAPI from "./useAPI";

export type StateWithCustom = State & { custom: { [key: string]: string | null | undefined } };

type Callback = (state: StateWithCustom) => unknown;

export default function useStateAPI(method: string, callback?: Callback | null) {
  const { updateState } = useContext(StateContext);

  const wrappedCallback = useCallback(
    (state: StateWithCustom) => {
      updateState(state);
      if (callback) {
        callback(state);
      }
    },
    [updateState, callback]
  );

  return useAPI(method, wrappedCallback);
}
