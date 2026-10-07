// @flow strict

import * as React from "react";
import Button from "react-bootstrap/Button";
import Modal from "react-bootstrap/Modal";
import FormControl from "react-bootstrap/FormControl";
import { useContext, useState } from "react";
import MessageContext from "./MessageContext";
import StateContext from "./StateContext";
import useAPI from "./useStateAPI";

type Props = {
  show: boolean,
  onClose: () => mixed,
};

export default function ImportEnrollmentModal({ show, onClose }: Props) {
  const [sheet, setSheet] = useState("");

  const { pushMessage } = useContext(MessageContext);
  const state = useContext(StateContext);
  const importEnrollmentFromSheet = useAPI("import_enrollment_from_sheet", () =>
    pushMessage("Import successful!")
  );

  return (
    <Modal show={show} onHide={() => onClose()}>
      <Modal.Header closeButton>
        <Modal.Title>Enter Spreadsheet URL</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        See this{" "}
        <a
          href="https://docs.google.com/spreadsheets/d/1rDdoRYD-7Cha2FNeZiMgrWlz8LfvZrBX7xyk_1lARdY/edit?usp=sharing"
          target="__blank"
        >
          sample spreadsheet
        </a>{" "}
        as an example.{" "}
        <p>
          Make sure to make it visible to anyone with the link
          {state.serviceAccountEmail != null ? (
            <>
              , or share it directly with{" "}
              <a href={`mailto:${state.serviceAccountEmail}`} target="__blank">
                {state.serviceAccountEmail}
              </a>
            </>
          ) : null}
          .
        </p>
        <FormControl
          value={sheet ?? ""}
          onChange={(e) => setSheet(e.target.value)}
          placeholder="Sheet URL"
        />
      </Modal.Body>
      <Modal.Footer>
        <Button
          variant="success"
          onClick={() => {
            importEnrollmentFromSheet({ url: sheet });
            onClose();
          }}
        >
          Import
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
