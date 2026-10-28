import Button from "react-bootstrap/Button";
import Modal from "react-bootstrap/Modal";
import FormControl from "react-bootstrap/FormControl";
import { useContext, useState } from "react";
import MessageContext from "./MessageContext";
import StateContext from "./StateContext";
import useAPI from "./useStateAPI";

type Props = {
  show: boolean;
  onClose: () => unknown;
};

export default function ImportSectionsModal({ show, onClose }: Props) {
  const [sheet, setSheet] = useState("");

  const { pushMessage } = useContext(MessageContext);
  const state = useContext(StateContext);
  const importSectionsFromSheet = useAPI(
    "import_sections_from_sheet",
    ({ custom }) =>
      pushMessage(`Import successful! ${custom?.message ?? ""}`, "success"),
  );

  return (
    <Modal show={show} onHide={() => onClose()}>
      <Modal.Header closeButton>
        <Modal.Title>Enter Spreadsheet URL</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        See this{" "}
        <a
          href="https://docs.google.com/spreadsheets/d/1gn4kZtjyctjJDQxQUzE4uPZ0InMA88AgbXhD-Dmyt7U/edit?usp=sharing"
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
        <p>
          You can import again after editing the spreadsheet. A row with the
          same type, day, time and location as an existing section updates that
          section (its staff, capacity, tags and self-enrollment) rather than
          adding a copy, and its students stay enrolled. Sections missing from
          the spreadsheet are kept; delete them from their section page.
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
            importSectionsFromSheet({ url: sheet });
            onClose();
          }}
        >
          Import
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
