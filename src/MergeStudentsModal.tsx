import { useCallback, useContext, useMemo, useRef, useState } from "react";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import Modal from "react-bootstrap/Modal";
import MessageContext, { type Message } from "./MessageContext";
import Messages from "./Messages";
import useStateAPI from "./useStateAPI";

type Props = {
  show: boolean;
  onClose: () => void;
};

export default function MergeStudentsModal({ show, onClose }: Props) {
  // The page's messages are hidden behind the modal, so errors are shown in
  // it instead. The success message goes to the page, which the modal closes onto.
  const { pushMessage: pushPageMessage } = useContext(MessageContext);
  const [errors, setErrors] = useState<Array<Message>>([]);
  const modalMessages = useMemo(
    () => ({
      pushMessage: (text: string) =>
        setErrors((current) => current.concat([{ text, variant: "danger" }])),
    }),
    [],
  );
  const close = () => {
    setErrors([]);
    onClose();
  };
  return (
    <MessageContext.Provider value={modalMessages}>
      <MergeStudentsForm
        show={show}
        onClose={close}
        errors={errors}
        setErrors={setErrors}
        pushPageMessage={pushPageMessage}
      />
    </MessageContext.Provider>
  );
}

function MergeStudentsForm({
  show,
  onClose,
  errors,
  setErrors,
  pushPageMessage,
}: Props & {
  errors: Array<Message>;
  setErrors: (errors: Array<Message>) => void;
  pushPageMessage: (text: string, variant: "success") => void;
}) {
  const [fromEmail, setFromEmail] = useState("");
  const [intoEmail, setIntoEmail] = useState("");
  const [merging, setMerging] = useState(false);
  // Clear the inputs whenever the modal closes.
  const [prevShow, setPrevShow] = useState(show);
  if (show !== prevShow) {
    setPrevShow(show);
    if (!show) {
      setFromEmail("");
      setIntoEmail("");
    }
  }

  // Set by the success callback, so the modal stays open after a failure,
  // showing its error.
  const merged = useRef(false);
  const merge = useStateAPI(
    "merge_students",
    useCallback(
      ({ custom }: { custom: { message?: string | null } }) => {
        merged.current = true;
        pushPageMessage(custom.message ?? "Merged.", "success");
      },
      [pushPageMessage],
    ),
  );

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrors([]);
    merged.current = false;
    setMerging(true);
    await merge({ from_email: fromEmail, into_email: intoEmail });
    setMerging(false);
    if (merged.current) {
      onClose();
    }
  };

  return (
    <Modal show={show} onHide={onClose}>
      <Form onSubmit={onSubmit}>
        <Modal.Header closeButton>
          <Modal.Title>Merge Students</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Messages messages={errors} onChange={setErrors} />
          <p>
            For a student who is in Sections twice, under two emails, because
            their email changed: once under an email no one has signed in with
            (from a spreadsheet import or added by staff), and once under the
            email they signed in with.
          </p>
          <p>
            Merging moves the first email&rsquo;s sections and attendance in
            this course to the second, and removes the first if it isn&rsquo;t
            in any other course. Nothing in other courses changes.
          </p>
          <Form.Group className="mb-3" controlId="merge-from-email">
            <Form.Label>
              Merge from (an email no one has signed in with)
            </Form.Label>
            <Form.Control
              type="email"
              required
              value={fromEmail}
              onChange={(e) => setFromEmail(e.target.value)}
            />
          </Form.Group>
          <Form.Group controlId="merge-into-email">
            <Form.Label>Into (the email they signed in with)</Form.Label>
            <Form.Control
              type="email"
              required
              value={intoEmail}
              onChange={(e) => setIntoEmail(e.target.value)}
            />
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" type="submit" disabled={merging}>
            {merging ? "Merging…" : "Merge"}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}
