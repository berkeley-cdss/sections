import { useCallback, useContext } from "react";
import type { SectionDetails } from "./models";
import SectionStateContext from "./SectionStateContext";
import useAPI from "./useAPI";

type Callback = (state: SectionDetails) => void;

export default function useSectionAPI(method: string, callback?: Callback | null) {
  const { updateState } = useContext(SectionStateContext);

  const wrappedCallback = useCallback(
    (state: SectionDetails) => {
      updateState(state);
      if (callback) {
        callback(state);
      }
    },
    [updateState, callback]
  );

  return useAPI(method, wrappedCallback);
}
